import json
import time
import azure.cognitiveservices.speech as speechsdk
import config
from src.utils import setup_logging

logger = setup_logging("transcriber")


def transcribe(audio_path: str, language: str) -> list[dict]:
    speech_config = speechsdk.SpeechConfig(
        subscription=config.AZURE_SPEECH_KEY,
        region=config.AZURE_SPEECH_REGION,
    )
    speech_config.speech_recognition_language = language
    speech_config.request_word_level_timestamps()
    speech_config.output_format = speechsdk.OutputFormat.Detailed

    audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    segments = []
    done = False
    segment_id = 0
    errors = []

    def on_recognized(evt):
        nonlocal segment_id
        result = evt.result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text.strip():
            start = result.offset / 10_000_000
            duration = result.duration / 10_000_000
            end = start + duration
            segment_id += 1
            segment = {
                "id": segment_id,
                "text": result.text,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
            }
            segments.append(segment)
            logger.info(f"Segment {segment_id}: [{start:.1f}s-{end:.1f}s] {result.text[:50]}...")

    def on_canceled(evt):
        nonlocal done
        details = evt.result.cancellation_details
        if details.reason == speechsdk.CancellationReason.EndOfStream:
            logger.info("Recognition reached end of stream.")
        elif details.reason == speechsdk.CancellationReason.Error:
            error_msg = f"ASR error: {details.error_details}"
            logger.error(error_msg)
            errors.append(error_msg)
        else:
            logger.warning(f"Recognition canceled: {details.reason}")
        done = True

    def on_session_stopped(evt):
        nonlocal done
        logger.info("Recognition session stopped.")
        done = True

    recognizer.recognized.connect(on_recognized)
    recognizer.canceled.connect(on_canceled)
    recognizer.session_stopped.connect(on_session_stopped)

    logger.info(f"Starting transcription: {audio_path} (language: {language})")
    recognizer.start_continuous_recognition()

    while not done:
        time.sleep(0.5)

    recognizer.stop_continuous_recognition()

    if errors:
        raise RuntimeError(f"Transcription failed: {'; '.join(errors)}")

    logger.info(f"Transcription complete: {len(segments)} raw segments")

    # Split long segments into ~MAX_SEGMENT_DURATION chunks
    segments = split_long_segments(segments, max_duration=10.0)
    logger.info(f"After splitting: {len(segments)} segments")

    return segments


def split_long_segments(segments: list[dict], max_duration: float = 10.0) -> list[dict]:
    """Split segments longer than max_duration into smaller ones at sentence boundaries.

    Uses punctuation (. ! ? ;) to find split points. Distributes time
    proportionally based on character count.
    """
    import re
    result = []
    new_id = 0

    for seg in segments:
        if seg["duration"] <= max_duration:
            new_id += 1
            result.append({**seg, "id": new_id})
            continue

        # Split text at sentence boundaries
        sentences = re.split(r'(?<=[.!?;])\s+', seg["text"].strip())
        if len(sentences) <= 1:
            # No sentence boundary found, keep as-is
            new_id += 1
            result.append({**seg, "id": new_id})
            continue

        # Group sentences into chunks that fit within max_duration
        total_chars = sum(len(s) for s in sentences)
        total_duration = seg["duration"]
        start = seg["start"]

        chunk_sentences = []
        chunk_chars = 0

        for sentence in sentences:
            estimated_chunk_duration = (chunk_chars + len(sentence)) / total_chars * total_duration

            # If adding this sentence exceeds max_duration and we already have content, flush
            if chunk_sentences and estimated_chunk_duration > max_duration:
                chunk_duration = chunk_chars / total_chars * total_duration
                end = round(start + chunk_duration, 3)
                new_id += 1
                result.append({
                    "id": new_id,
                    "text": " ".join(chunk_sentences),
                    "start": round(start, 3),
                    "end": end,
                    "duration": round(chunk_duration, 3),
                })
                start = end
                chunk_sentences = []
                chunk_chars = 0

            chunk_sentences.append(sentence)
            chunk_chars += len(sentence)

        # Flush remaining
        if chunk_sentences:
            end = seg["end"]
            new_id += 1
            result.append({
                "id": new_id,
                "text": " ".join(chunk_sentences),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
            })

    return result


def save_transcript(segments: list[dict], output_path: str) -> str:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    logger.info(f"Transcript saved: {output_path}")
    return output_path
