import os
import yt_dlp
from src.utils import setup_logging, ensure_dir

logger = setup_logging("downloader")


def download_video(url: str, output_dir: str) -> str:
    if not url:
        raise ValueError("URL cannot be empty")

    ensure_dir(output_dir)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
    }

    logger.info(f"Downloading video from: {url}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "video")
        ext = info.get("ext", "mp4")
        filepath = os.path.join(output_dir, f"{video_id}.{ext}")

        if not os.path.exists(filepath):
            for f in os.listdir(output_dir):
                if f.startswith(video_id):
                    filepath = os.path.join(output_dir, f)
                    break

    if not os.path.exists(filepath):
        raise RuntimeError(f"Download failed: file not found at {filepath}")

    logger.info(f"Downloaded: {filepath}")
    return filepath


def get_video_id(url: str) -> str:
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("id", "video")
