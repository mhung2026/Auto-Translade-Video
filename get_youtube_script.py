"""Lấy script (phụ đề) video YouTube nhanh nhất — chỉ text thuần.

Chiến lược:
    1. Thử youtube-transcript-api (lấy captions có sẵn, gần như tức thì)
    2. Fallback sang yt-dlp subtitle nếu captions không có

Usage:
    python get_youtube_script.py URL [URL2 ...]
    python get_youtube_script.py --file urls.txt
    python get_youtube_script.py URL --lang vi
    python get_youtube_script.py URL --output script.txt
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

# Ensure stdout/stderr use UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)


def extract_video_id(url: str) -> str | None:
    """Lấy video ID từ URL YouTube."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


def fetch_via_api(video_id: str, languages: list[str]) -> tuple[str, str] | None:
    """Lấy transcript bằng youtube-transcript-api. Trả về (text, lang) hoặc None."""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        # Ưu tiên: manual (người tạo chữ) theo ngôn ngữ yêu cầu
        for lang in languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                fetched = transcript.fetch()
                text = " ".join(s.text for s in fetched if s.text.strip())
                return text, f"{lang} (manual)"
            except NoTranscriptFound:
                continue

        # Kế tiếp: auto-generated theo ngôn ngữ yêu cầu
        for lang in languages:
            try:
                transcript = transcript_list.find_generated_transcript([lang])
                fetched = transcript.fetch()
                text = " ".join(s.text for s in fetched if s.text.strip())
                return text, f"{lang} (auto)"
            except NoTranscriptFound:
                continue

        # Cuối cùng: transcript bất kỳ + dịch nếu có
        for transcript in transcript_list:
            fetched = transcript.fetch()
            text = " ".join(s.text for s in fetched if s.text.strip())
            return text, f"{transcript.language_code} ({'auto' if transcript.is_generated else 'manual'})"

    except (TranscriptsDisabled, VideoUnavailable) as e:
        print(f"  API lỗi: {type(e).__name__}")
        return None
    except Exception as e:
        print(f"  API lỗi: {e}")
        return None

    return None


def fetch_via_ytdlp(url: str, languages: list[str]) -> tuple[str, str] | None:
    """Fallback: dùng yt-dlp để lấy subtitle. Trả về (text, lang) hoặc None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lang_str = ",".join(languages) + ",en"
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--write-subs",
            "--sub-langs", lang_str,
            "--sub-format", "vtt",
            "-o", os.path.join(tmpdir, "%(id)s.%(ext)s"),
            url,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  yt-dlp lỗi: {result.stderr[:200]}")
            return None

        # Tìm file .vtt
        vtt_files = [f for f in os.listdir(tmpdir) if f.endswith(".vtt")]
        if not vtt_files:
            return None

        # Ưu tiên theo ngôn ngữ yêu cầu
        vtt_file = None
        used_lang = None
        for lang in languages + ["en"]:
            for f in vtt_files:
                if f".{lang}." in f:
                    vtt_file = os.path.join(tmpdir, f)
                    used_lang = lang
                    break
            if vtt_file:
                break

        if not vtt_file:
            vtt_file = os.path.join(tmpdir, vtt_files[0])
            used_lang = "unknown"

        with open(vtt_file, "r", encoding="utf-8") as f:
            vtt_content = f.read()

        text = parse_vtt_to_text(vtt_content)
        return text, f"{used_lang} (yt-dlp)"


def parse_vtt_to_text(vtt_content: str) -> str:
    """Parse VTT format → plain text (loại timestamps, tags, duplicate lines)."""
    lines = []
    seen = set()
    for line in vtt_content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        # Loại tags như <c>, <00:00:01.000>
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)
    return " ".join(lines)


def get_script(url: str, languages: list[str]) -> tuple[str, str] | None:
    """Lấy script cho 1 URL. Thử API trước, fallback yt-dlp."""
    video_id = extract_video_id(url)
    if not video_id:
        print(f"  Không phân tích được video ID từ URL")
        return None

    print(f"  Video ID: {video_id}")

    # Thử youtube-transcript-api
    result = fetch_via_api(video_id, languages)
    if result:
        return result

    # Fallback yt-dlp
    print(f"  Thử yt-dlp...")
    return fetch_via_ytdlp(url, languages)


def main():
    parser = argparse.ArgumentParser(description="Lấy script YouTube thành plain text")
    parser.add_argument("urls", nargs="*", help="URL video YouTube (có thể nhiều URL)")
    parser.add_argument("--file", help="Đọc URLs từ file (mỗi URL 1 dòng)")
    parser.add_argument(
        "--lang",
        default="en,vi,ja",
        help="Ngôn ngữ ưu tiên, phân cách dấu phẩy (mặc định: en,vi,ja)",
    )
    parser.add_argument(
        "--output", "-o",
        help="File output (nếu 1 URL: ghi ra 1 file; nếu nhiều URL: là thư mục)",
    )
    args = parser.parse_args()

    urls = list(args.urls)
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            urls.extend(line.strip() for line in f if line.strip() and not line.startswith("#"))

    if not urls:
        parser.error("Cần ít nhất 1 URL (tham số hoặc --file)")

    languages = [l.strip() for l in args.lang.split(",") if l.strip()]

    print(f"Tổng: {len(urls)} video(s) | Ngôn ngữ ưu tiên: {languages}")
    print("=" * 60)

    output_is_dir = len(urls) > 1 or (args.output and os.path.isdir(args.output))
    if output_is_dir and args.output:
        os.makedirs(args.output, exist_ok=True)

    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] {url}")
        result = get_script(url, languages)

        if not result:
            print(f"  THẤT BẠI")
            continue

        text, used_lang = result
        print(f"  OK: {len(text)} ký tự ({used_lang})")

        # Quyết định đường dẫn output
        if args.output:
            if output_is_dir:
                video_id = extract_video_id(url) or f"video_{i}"
                out_path = os.path.join(args.output, f"{video_id}.txt")
            else:
                out_path = args.output
        else:
            video_id = extract_video_id(url) or f"video_{i}"
            out_path = f"{video_id}.txt"

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  Saved: {out_path}")

    print("\n" + "=" * 60)
    print("DONE")


if __name__ == "__main__":
    main()
