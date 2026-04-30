import os
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
from xml.sax.saxutils import escape as xml_escape
import config
from src.utils import setup_logging

logger = setup_logging("synthesizer")


def _build_ssml(text: str, voice: str, rate: str = "+0%", reduce_pauses: bool = True) -> str:
    safe_text = xml_escape(text)

    if reduce_pauses:
        # Wrap text in prosody with reduced pauses: use a tight <break> between sentences
        # and set silence attributes to minimize inter-word gaps
        inner = (
            f'<prosody rate="{rate}">'
            f'<mstts:silence type="Sentenceboundary" value="100ms"/>'
            f'<mstts:silence type="Comma-Semicolon" value="50ms"/>'
            f'{safe_text}'
            f'</prosody>'
        )
    else:
        inner = f'<prosody rate="{rate}">{safe_text}</prosody>'

    return (
        f'<speak version="1.0" '
        f'xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xmlns:mstts="http://www.w3.org/2001/mstts" '
        f'xml:lang="ja-JP">'
        f'<voice name="{voice}">'
        f'{inner}'
        f'</voice>'
        f'</speak>'
    )


def synthesize_segment(
    text_jp: str,
    output_path: str,
    target_duration: float | None = None,
    voice: str | None = None,
) -> dict:
    voice = voice or config.TTS_VOICE

    speech_config = speechsdk.SpeechConfig(
        subscription=config.AZURE_SPEECH_KEY,
        region=config.AZURE_SPEECH_REGION,
    )
    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)

    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    max_ratio = config.TTS_MAX_SPEED_RATIO  # default 1.3 (130%)
    final_rate = "+0%"

    # --- Step 1: Estimate optimal initial rate based on text length and target duration ---
    # Japanese speech: ~7-8 chars/sec at normal speed
    chars_per_sec_normal = 7.5
    estimated_normal_duration = len(text_jp) / chars_per_sec_normal

    if target_duration and estimated_normal_duration > 0:
        # Pre-calculate rate to fit target duration on first try
        estimated_ratio = estimated_normal_duration / target_duration
        if estimated_ratio > 1.0:
            # Need to speed up — cap at max_ratio
            initial_ratio = min(estimated_ratio, max_ratio)
            rate_percent = int((initial_ratio - 1) * 100)
            initial_rate = f"+{rate_percent}%"
        else:
            initial_rate = "+0%"
    else:
        initial_rate = "+0%"

    # --- Step 2: First TTS pass with estimated rate + reduced pauses ---
    final_rate = initial_rate
    ssml = _build_ssml(text_jp, voice, rate=final_rate, reduce_pauses=True)
    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(f"TTS failed: {details.reason} — {details.error_details}")

    audio = AudioSegment.from_wav(output_path)
    actual_duration = len(audio) / 1000.0
    speed_adjusted = final_rate != "+0%"

    # --- Step 3: If still too long, re-synthesize with adjusted rate ---
    if target_duration and actual_duration > target_duration * 1.05:  # 5% tolerance
        ratio = actual_duration / target_duration
        if ratio <= max_ratio:
            rate_percent = int((ratio - 1) * 100)
            final_rate = f"+{rate_percent}%"
            logger.info(
                f"Re-adjusting speed: {actual_duration:.1f}s → ~{target_duration:.1f}s "
                f"(rate: {final_rate})"
            )

            ssml = _build_ssml(text_jp, voice, rate=final_rate, reduce_pauses=True)
            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                raise RuntimeError(f"TTS retry failed: {details.reason}")

            audio = AudioSegment.from_wav(output_path)
            actual_duration = len(audio) / 1000.0
            speed_adjusted = True
        else:
            # Apply max speed as a last resort
            final_rate = f"+{int((max_ratio - 1) * 100)}%"
            logger.warning(
                f"Segment too long ({ratio:.1f}x > {max_ratio}x cap). "
                f"Capping at {final_rate} — user should adjust in CapCut."
            )

            ssml = _build_ssml(text_jp, voice, rate=final_rate, reduce_pauses=True)
            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                raise RuntimeError(f"TTS max-speed retry failed: {details.reason}")

            audio = AudioSegment.from_wav(output_path)
            actual_duration = len(audio) / 1000.0
            speed_adjusted = True

    return {
        "path": output_path,
        "actual_duration": round(actual_duration, 3),
        "speed_adjusted": speed_adjusted,
        "rate_applied": final_rate,
    }
