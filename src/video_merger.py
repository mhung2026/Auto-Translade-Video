import os
import subprocess
from src.utils import setup_logging

logger = setup_logging("video_merger")


def merge_video(video_path: str, audio_path: str, output_path: str) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-map", "0:v",
        "-map", "1:a",
        "-y",
        output_path,
    ]

    logger.info(f"Merging video + audio → {output_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

    logger.info(f"Video merged: {output_path}")
    return output_path
