import os
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
import config
from src.utils import setup_logging

logger = setup_logging("synthesizer")


def _build_ssml(text: str, voice: str, rate: str = "+0%") -> str:
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP">'
        f'<voice name="{voice}">'
        f'<prosody rate="{rate}">'
        f'{text}'
        f'</prosody>'
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

    ssml = _build_ssml(text_jp, voice)
    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(f"TTS failed: {details.reason} — {details.error_details}")

    audio = AudioSegment.from_wav(output_path)
    actual_duration = len(audio) / 1000.0
    speed_adjusted = False

    if target_duration and actual_duration > target_duration:
        ratio = actual_duration / target_duration
        max_ratio = config.TTS_MAX_SPEED_RATIO

        if ratio <= max_ratio:
            rate_percent = int((ratio - 1) * 100)
            rate_str = f"+{rate_percent}%"
            logger.info(
                f"Adjusting speed: {actual_duration:.1f}s → ~{target_duration:.1f}s "
                f"(rate: {rate_str})"
            )

            ssml = _build_ssml(text_jp, voice, rate=rate_str)
            result = synthesizer.speak_ssml_async(ssml).get()

            if result.reason == speechsdk.ResultReason.Canceled:
                details = result.cancellation_details
                raise RuntimeError(f"TTS retry failed: {details.reason}")

            audio = AudioSegment.from_wav(output_path)
            actual_duration = len(audio) / 1000.0
            speed_adjusted = True
        else:
            logger.warning(
                f"Segment too long ({ratio:.1f}x > {max_ratio}x). "
                f"Keeping default speed — user should adjust in CapCut."
            )

    return {
        "path": output_path,
        "actual_duration": round(actual_duration, 3),
        "speed_adjusted": speed_adjusted,
    }
