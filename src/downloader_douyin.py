"""Douyin downloader using a headless Chromium (Playwright).

Background: as of 2025+ yt-dlp's Douyin/TikTok extractor is broken because the
detail endpoint (`/aweme/v1/web/aweme/detail/`) requires an `a_bogus` /
`msToken` / `x-secsdk-web-signature` signature triplet that yt-dlp cannot
generate — every request returns an empty body and the extractor surfaces
"Fresh cookies (not necessarily logged in) are needed".

Workaround: load the video page in a real browser (no login needed), intercept
the DASH segment requests it issues to `*.zjcdn.com/.../media-video-*/` and
`media-audio-*/`, then download those direct CDN URLs with `requests` and mux
them with ffmpeg.

Requires: playwright + chromium (`pip install playwright && playwright install
chromium`), ffmpeg on PATH.
"""
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from src.utils import setup_logging, ensure_dir

logger = setup_logging("downloader_douyin")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
_REFERER = "https://www.douyin.com/"

_DASH_VIDEO_RE = re.compile(r"/media-video-")
_DASH_AUDIO_RE = re.compile(r"/media-audio-")
_CDN_HOST_RE = re.compile(r"\.(zjcdn|douyinvod|douyincdn)\.com|\.bytecdntp\.com")
_VIDEO_MIME_RE = re.compile(r"mime_type=video_mp4")
_VIDEO_ID_RE = re.compile(r"/video/(\d+)")


def is_douyin_url(url: str) -> bool:
    if not url:
        return False
    host = urllib.parse.urlparse(url.strip()).netloc.lower()
    return host == "douyin.com" or host.endswith(".douyin.com")


def _bitrate_of(url: str) -> int:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    try:
        return int(qs.get("br", ["0"])[0])
    except (ValueError, TypeError):
        return 0


def _extract_via_playwright(
    url: str,
    wait_seconds: float = 20.0,
    headless: bool = True,
) -> dict:
    """Open the Douyin page and capture direct CDN URLs for video + audio.

    Douyin detects vanilla headless Chromium and refuses to start the player
    (the browser sits on the page but never fetches media segments). We launch
    with `--disable-blink-features=AutomationControlled` and a fully populated
    UA + viewport to look like a real browser. If that still fails on a
    particular host, callers can pass `headless=False` to fall back to a
    visible window.
    """
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=launch_args)
        context = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        # Hide webdriver flag — Douyin checks navigator.webdriver
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()

        captured = {"dash_video": [], "dash_audio": [], "progressive": []}

        def on_request(req):
            u = req.url
            if not _CDN_HOST_RE.search(u):
                return
            if _DASH_VIDEO_RE.search(u):
                captured["dash_video"].append(u)
            elif _DASH_AUDIO_RE.search(u):
                captured["dash_audio"].append(u)
            elif _VIDEO_MIME_RE.search(u):
                captured["progressive"].append(u)

        page.on("request", on_request)

        logger.info(f"Loading Douyin page: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if captured["progressive"] or (captured["dash_video"] and captured["dash_audio"]):
                break
            page.wait_for_timeout(500)

        title = page.title() or ""
        title = re.sub(r"\s*[-–]\s*抖音\s*$", "", title).strip()
        canonical = page.url

        browser.close()

    logger.info(
        f"Captured: progressive={len(captured['progressive'])} "
        f"dash_video={len(captured['dash_video'])} dash_audio={len(captured['dash_audio'])}"
    )

    m = _VIDEO_ID_RE.search(canonical)
    video_id = m.group(1) if m else ""

    if captured["progressive"]:
        return {
            "mode": "progressive",
            "canonical_url": canonical,
            "video_id": video_id,
            "title": title,
            "video_url": max(captured["progressive"], key=_bitrate_of),
        }

    if captured["dash_video"] and captured["dash_audio"]:
        return {
            "mode": "dash",
            "canonical_url": canonical,
            "video_id": video_id,
            "title": title,
            "video_url": max(captured["dash_video"], key=_bitrate_of),
            "audio_url": max(captured["dash_audio"], key=_bitrate_of),
        }

    raise RuntimeError(
        f"No usable video stream captured from Douyin page (canonical={canonical})"
    )


def _download_stream(url: str, dest: Path) -> int:
    headers = {"User-Agent": _UA, "Referer": _REFERER}
    size = 0
    with requests.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    size += len(chunk)
    return size


def _ffmpeg_mux(video_path: Path, audio_path: Path, output_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c", "copy",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-500:]}")


def _ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            text=True,
        )
        return float(out.strip())
    except Exception:
        return 0.0


def download_douyin(
    url: str,
    output_dir: str,
    filename: str | None = None,
) -> dict:
    """Download a Douyin video and return metadata matching download_one() shape.

    Returned dict keys:
        input_url, canonical_url, platform, video_id, title, uploader,
        duration, filepath
    """
    if not url:
        raise ValueError("URL cannot be empty")

    ensure_dir(output_dir)

    info = _extract_via_playwright(url)
    video_id = info["video_id"] or "unknown"

    out_dir = Path(output_dir)
    name = filename or f"Douyin_{video_id}.mp4"
    final_path = out_dir / name

    if info["mode"] == "progressive":
        logger.info(f"Downloading progressive MP4 id={video_id}")
        size = _download_stream(info["video_url"], final_path)
        logger.info(f"Stream downloaded: {size:,}B")
    else:
        tmp_video = out_dir / f"_tmp_{video_id}.video.mp4"
        tmp_audio = out_dir / f"_tmp_{video_id}.audio.m4a"
        try:
            logger.info(f"Downloading DASH video stream id={video_id}")
            v_size = _download_stream(info["video_url"], tmp_video)
            logger.info(f"Downloading DASH audio stream id={video_id}")
            a_size = _download_stream(info["audio_url"], tmp_audio)
            logger.info(f"Streams downloaded: video={v_size:,}B audio={a_size:,}B")
            _ffmpeg_mux(tmp_video, tmp_audio, final_path)
        finally:
            for p in (tmp_video, tmp_audio):
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

    duration = _ffprobe_duration(final_path)
    logger.info(f"Saved: {final_path} ({duration:.1f}s)")

    return {
        "input_url": url,
        "canonical_url": info["canonical_url"],
        "platform": "Douyin",
        "video_id": video_id,
        "title": info["title"],
        "uploader": "",
        "duration": duration,
        "filepath": str(final_path),
    }
