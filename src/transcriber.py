import json
import config
from src.utils import setup_logging

logger = setup_logging("transcriber")


def _short_lang(language: str) -> str:
    """Convert a locale like 'zh-CN'/'en-US'/'ja-JP' to a WhisperX code 'zh'/'en'/'ja'."""
    return language.split("-")[0].lower()


def transcribe(audio_path: str, language: str) -> list[dict]:
    """Transcribe audio with WhisperX, returning word-aligned segments.

    Output matches the original Azure contract: a list of
    {id, text, start, end, duration}. WhisperX gives segment-level text from
    faster-whisper, then forced phoneme alignment (wav2vec2) refines the
    start/end to word-level accuracy — which the dubbing timeline relies on.
    """
    import whisperx

    lang = _short_lang(language)
    device = config.WHISPER_DEVICE
    compute_type = config.WHISPER_COMPUTE_TYPE
    model_size = config.WHISPER_MODEL

    logger.info(
        f"Loading WhisperX model '{model_size}' on {device} ({compute_type}), language={lang}"
    )
    model = whisperx.load_model(model_size, device, compute_type=compute_type, language=lang)

    audio = whisperx.load_audio(audio_path)
    logger.info(f"Transcribing: {audio_path}")
    result = model.transcribe(audio, batch_size=16, language=lang)
    raw_segments = result.get("segments", [])
    logger.info(f"Transcription complete: {len(raw_segments)} raw segments")

    # Forced alignment for accurate word/segment boundaries. Non-fatal: if the
    # alignment model is unavailable for this language, fall back to the
    # faster-whisper segment timestamps.
    try:
        align_model, metadata = whisperx.load_align_model(language_code=lang, device=device)
        result = whisperx.align(
            raw_segments, align_model, metadata, audio, device,
            return_char_alignments=False,
        )
        raw_segments = result.get("segments", raw_segments)
        logger.info("Word-level alignment applied")
    except Exception as e:
        logger.warning(f"Alignment unavailable for '{lang}' ({e}); using segment-level timestamps")

    segments = []
    segment_id = 0
    for seg in raw_segments:
        text = (seg.get("text") or "").strip()
        start = seg.get("start")
        end = seg.get("end")
        if not text or start is None or end is None:
            continue
        start = float(start)
        end = float(end)
        if end <= start:
            continue
        segment_id += 1
        segments.append({
            "id": segment_id,
            "text": text,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
        })
        logger.info(f"Segment {segment_id}: [{start:.1f}s-{end:.1f}s] {text[:50]}...")

    if not segments:
        raise RuntimeError("Transcription produced no usable segments")

    # Split long segments into ~max_duration chunks at sentence boundaries
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
