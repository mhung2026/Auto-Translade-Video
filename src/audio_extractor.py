import os
import subprocess
import config
from src.utils import setup_logging

logger = setup_logging("audio_extractor")


def extract_audio(video_path: str, output_path: str) -> str:
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    sample_rate = str(config.AUDIO_SAMPLE_RATE)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",
        "-ar", sample_rate,
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-y",
        output_path,
    ]

    logger.info(f"Extracting audio: {video_path} → {output_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Audio extraction produced empty file: {output_path}")

    logger.info(f"Audio extracted: {output_path} ({os.path.getsize(output_path)} bytes)")
    return output_path
