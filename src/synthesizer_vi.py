"""Vietnamese TTS Synthesizer using LucyLab API.

Flow:
    1. POST ttsLongText → get projectExportId
    2. Poll getExportStatus until state == "completed"
    3. Download audio from returned URL
"""
import os
import time
import requests
from pydub import AudioSegment
import config
from src.utils import setup_logging

logger = setup_logging("synthesizer_vi")

POLL_INTERVAL = 2  # seconds between status checks
POLL_TIMEOUT = 120  # max seconds to wait for TTS completion


def _call_lucylab(method: str, input_data: dict) -> dict:
    """Call LucyLab JSON-RPC API."""
    response = requests.post(
        config.LUCYLAB_API_URL,
        headers={
            "Authorization": f"Bearer {config.VIETNAMESE_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "method": method,
            "input": input_data,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"LucyLab API error: {data['error']}")

    return data.get("result", {})


def _wait_for_audio(export_id: str) -> str:
    """Poll getExportStatus until completed, return audio URL."""
    start = time.time()

    while time.time() - start < POLL_TIMEOUT:
        result = _call_lucylab("getExportStatus", {"projectExportId": export_id})
        state = result.get("state", "")

        if state == "completed":
            url = result.get("url", "")
            if not url:
                raise RuntimeError("TTS completed but no audio URL returned")
            return url

        if state == "failed":
            raise RuntimeError(f"TTS job failed: {result}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"TTS polling timed out after {POLL_TIMEOUT}s for export {export_id}")


def _download_audio(url: str, output_path: str) -> str:
    """Download audio file from URL."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    return output_path


def synthesize_segment_vi(
    text_vi: str,
    output_path: str,
    target_duration: float | None = None,
    voice_id: str | None = None,
) -> dict:
    """Synthesize Vietnamese text to audio using LucyLab API.

    Args:
        text_vi: Vietnamese text to speak
        output_path: Where to save the WAV file
        target_duration: Target duration in seconds (for speed adjustment)
        voice_id: LucyLab voice ID (default from config)

    Returns:
        dict with path, actual_duration, speed_adjusted, rate_applied
    """
    if not voice_id:
        raise ValueError("voice_id is required. Use --voice male/female or set VIETNAMESE_VOICEID_MALE/FEMALE in .env")
    if not config.VIETNAMESE_API_KEY:
        raise ValueError("VIETNAMESE_API_KEY not set in .env")

    max_speed = config.VIETNAMESE_TTS_MAX_SPEED

    # --- Step 1: Estimate optimal speed based on text length and target duration ---
    # Vietnamese speech: ~5-6 syllables/sec at normal speed
    # Approximate: 1 Vietnamese word ≈ 1-2 syllables, ~4-5 words/sec
    chars_per_sec_normal = 12.0  # Vietnamese characters per second at 1.0x
    estimated_normal_duration = len(text_vi) / chars_per_sec_normal

    speed = 1.0
    if target_duration and estimated_normal_duration > 0:
        estimated_ratio = estimated_normal_duration / target_duration
        if estimated_ratio > 1.0:
            speed = min(estimated_ratio, max_speed)
            speed = round(speed, 2)

    # --- Step 2: Call TTS API ---
    logger.info(f"TTS request: {len(text_vi)} chars, speed={speed}, target={target_duration:.1f}s"
                if target_duration else f"TTS request: {len(text_vi)} chars, speed={speed}")

    result = _call_lucylab("ttsLongText", {
        "text": text_vi,
        "userVoiceId": voice_id,
        "speed": speed,
    })

    export_id = result.get("projectExportId")
    if not export_id:
        raise RuntimeError(f"No projectExportId in response: {result}")

    logger.info(f"TTS job created: {export_id} (chars={result.get('characterCount', '?')}, "
                f"blocks={result.get('blockCount', '?')})")

    # --- Step 3: Poll for completion and download ---
    audio_url = _wait_for_audio(export_id)
    logger.info(f"TTS completed, downloading audio...")

    # Download to a temp file first (API may return mp3 or wav)
    temp_path = output_path + ".tmp"
    _download_audio(audio_url, temp_path)

    # Convert to WAV for consistency with the rest of the pipeline
    audio = AudioSegment.from_file(temp_path)
    audio.export(output_path, format="wav")
    os.remove(temp_path)

    actual_duration = len(audio) / 1000.0
    speed_adjusted = speed != 1.0

    # --- Step 4: If still too long, we can't re-synthesize easily (API cost),
    # just log a warning for CapCut adjustment ---
    if target_duration and actual_duration > target_duration * 1.1:
        if speed < max_speed:
            # Try once more with higher speed
            new_speed = min(actual_duration / target_duration * speed, max_speed)
            new_speed = round(new_speed, 2)
            logger.info(
                f"Re-adjusting speed: {actual_duration:.1f}s → ~{target_duration:.1f}s "
                f"(speed: {speed} → {new_speed})"
            )

            result2 = _call_lucylab("ttsLongText", {
                "text": text_vi,
                "userVoiceId": voice_id,
                "speed": new_speed,
            })

            export_id2 = result2.get("projectExportId")
            if export_id2:
                audio_url2 = _wait_for_audio(export_id2)
                _download_audio(audio_url2, temp_path)
                audio = AudioSegment.from_file(temp_path)
                audio.export(output_path, format="wav")
                os.remove(temp_path)
                actual_duration = len(audio) / 1000.0
                speed = new_speed
                speed_adjusted = True
        else:
            logger.warning(
                f"Segment too long ({actual_duration:.1f}s vs {target_duration:.1f}s target). "
                f"Already at max speed {max_speed}x — adjust in CapCut."
            )

    return {
        "path": output_path,
        "actual_duration": round(actual_duration, 3),
        "speed_adjusted": speed_adjusted,
        "rate_applied": f"{speed}x",
    }
