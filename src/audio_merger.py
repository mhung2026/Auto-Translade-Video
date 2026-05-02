import os
import shutil
import subprocess

from pydub import AudioSegment

from src.utils import setup_logging, ensure_dir

logger = setup_logging("audio_merger")


def fit_segments_to_timeline(
    segments: list[dict],
    src_dir: str,
    dst_dir: str,
    max_speedup: float = 1.4,
    tolerance_s: float = 0.1,
) -> list[dict]:
    """Compress segments whose audio overflows into the next segment's start time.

    The merger overlays each segment at its original start timestamp, so if a
    segment's rendered audio is longer than the gap before the next segment
    begins, the tail audibly bleeds into the next line. This function applies
    ffmpeg `atempo` to speed up only the overflowing segments just enough to
    fit, capped at `max_speedup` to keep voice intelligible. Segments that fit
    are copied unchanged.

    The last segment has no successor, so it is never compressed here.

    Args:
        segments: ordered list of dicts with id, start, end, duration
        src_dir: directory containing seg_NNN.wav files
        dst_dir: directory to write the fitted seg_NNN.wav files
        max_speedup: max atempo ratio (default 1.4 = +40%)
        tolerance_s: overflows below this many seconds are ignored

    Returns:
        list of adjustment records:
            {id, available, before, after, speed, status}
        status is "OK" (no change), "FIT" (compressed and now fits),
        or "STILL_OVERFLOWS" (capped at max_speedup, will still bleed).
    """
    ensure_dir(dst_dir)
    adjustments: list[dict] = []

    for i, seg in enumerate(segments):
        src = os.path.join(src_dir, f"seg_{seg['id']:03d}.wav")
        dst = os.path.join(dst_dir, f"seg_{seg['id']:03d}.wav")

        if not os.path.exists(src):
            logger.warning(f"Segment file missing: {src}")
            continue

        actual_s = len(AudioSegment.from_wav(src)) / 1000.0

        if i + 1 < len(segments):
            available_s = segments[i + 1]["start"] - seg["start"]
        else:
            available_s = float("inf")

        if actual_s <= available_s + tolerance_s:
            shutil.copyfile(src, dst)
            adjustments.append({
                "id": seg["id"],
                "available": round(available_s, 2) if available_s != float("inf") else None,
                "before": round(actual_s, 2),
                "after": round(actual_s, 2),
                "speed": 1.0,
                "status": "OK",
            })
            continue

        target_ratio = actual_s / available_s
        speed = min(target_ratio, max_speedup)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-filter:a", f"atempo={speed:.3f}", dst],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.error(
                f"atempo failed on seg {seg['id']} (speed={speed:.2f}): "
                f"{result.stderr[:200]}"
            )
            shutil.copyfile(src, dst)
            adjustments.append({
                "id": seg["id"],
                "available": round(available_s, 2),
                "before": round(actual_s, 2),
                "after": round(actual_s, 2),
                "speed": 1.0,
                "status": "FFMPEG_ERROR",
            })
            continue

        new_dur_s = len(AudioSegment.from_wav(dst)) / 1000.0
        status = "FIT" if new_dur_s <= available_s + tolerance_s else "STILL_OVERFLOWS"

        msg = (
            f"Seg {seg['id']}: {actual_s:.2f}s > {available_s:.2f}s gap, "
            f"sped {speed:.2f}x -> {new_dur_s:.2f}s [{status}]"
        )
        if status == "STILL_OVERFLOWS":
            logger.warning(msg)
        else:
            logger.info(msg)

        adjustments.append({
            "id": seg["id"],
            "available": round(available_s, 2),
            "before": round(actual_s, 2),
            "after": round(new_dur_s, 2),
            "speed": round(speed, 3),
            "status": status,
        })

    fit_count = sum(1 for a in adjustments if a["status"] == "FIT")
    overflow_count = sum(1 for a in adjustments if a["status"] == "STILL_OVERFLOWS")
    logger.info(
        f"Timeline fit: {len(adjustments)} segments | "
        f"{fit_count} compressed to fit | "
        f"{overflow_count} still overflow (above {max_speedup}x cap)"
    )
    return adjustments


def merge_segments(
    segments: list[dict],
    segment_dir: str,
    output_path: str,
    total_duration: float,
    background_path: str | None = None,
    background_gain_db: float = 0.0,
) -> str:
    """Mix per-segment dub audio onto a background track.

    ``background_path`` may point to a clean instrumental (Demucs ``no_vocals``)
    or to the unmodified ``original_audio.wav``; in the latter case set
    ``background_gain_db`` to a negative value (e.g. -12.0 ≈ 25% volume) so the
    original speech sits under the new narration instead of competing with it.
    """
    total_ms = int(total_duration * 1000)
    if background_path:
        merged = _load_background(background_path, total_ms, background_gain_db)
    else:
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
    if background_path:
        gain_note = f" (gain {background_gain_db:+.1f} dB)" if background_gain_db else ""
        bg_label = f"with BGM{gain_note}"
    else:
        bg_label = "silent base"
    logger.info(
        f"Audio merged ({bg_label}): {output_path} "
        f"({len(segments)} segments, {total_duration:.1f}s)"
    )
    return output_path


def _load_background(
    background_path: str, total_ms: int, gain_db: float = 0.0
) -> AudioSegment:
    """Load a background track, apply gain, and pad/truncate it to ``total_ms``.

    Falls back to silent base if the file is missing or unreadable so a
    pipeline failure in vocal separation never aborts the merge.
    """
    if not os.path.exists(background_path):
        logger.warning(f"Background not found: {background_path}; using silent base")
        return AudioSegment.silent(duration=total_ms)

    try:
        bg = AudioSegment.from_wav(background_path)
    except Exception as exc:
        logger.warning(f"Failed to load background {background_path}: {exc}; using silent base")
        return AudioSegment.silent(duration=total_ms)

    if gain_db != 0.0:
        bg = bg.apply_gain(gain_db)

    if len(bg) < total_ms:
        bg = bg + AudioSegment.silent(duration=total_ms - len(bg))
    elif len(bg) > total_ms:
        bg = bg[:total_ms]
    return bg
