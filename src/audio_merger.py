import os
from pydub import AudioSegment
from src.utils import setup_logging

logger = setup_logging("audio_merger")


def merge_segments(
    segments: list[dict],
    segment_dir: str,
    output_path: str,
    total_duration: float,
) -> str:
    total_ms = int(total_duration * 1000)
    merged = AudioSegment.silent(duration=total_ms)

    for seg in segments:
        seg_file = os.path.join(segment_dir, f"seg_{seg['id']:03d}.wav")
        if not os.path.exists(seg_file):
            logger.warning(f"Segment file not found: {seg_file}, skipping")
            continue

        segment_audio = AudioSegment.from_wav(seg_file)
        start_ms = int(seg["start"] * 1000)

        merged = merged.overlay(segment_audio, position=start_ms)
        logger.debug(f"Placed segment {seg['id']} at {seg['start']:.1f}s")

    merged.export(output_path, format="wav")
    logger.info(
        f"Audio merged: {output_path} ({len(segments)} segments, {total_duration:.1f}s)"
    )
    return output_path
