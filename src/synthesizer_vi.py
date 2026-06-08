"""Vietnamese TTS Synthesizer using local VieNeu-TTS.

Runs entirely on CPU (ONNX, torch-free) — no API key, no network. The model is
loaded once and cached at module level because the pipeline calls
synthesize_segment_vi once per segment.

A voice id may be either a VieNeu preset voice name (e.g. "Xuân Vĩnh") or a path
to a 3-5s reference .wav for zero-shot cloning. Speed is not adjusted here: the
pipeline already fits each segment to the timeline with ffmpeg atempo.
"""
import os
from pydub import AudioSegment
import config
from src.utils import setup_logging

logger = setup_logging("synthesizer_vi")

_TTS = None
_PRESET_VOICES: list[tuple[str, str]] = []


def _get_tts():
    """Lazily load and cache the VieNeu model (expensive — load once)."""
    global _TTS, _PRESET_VOICES
    if _TTS is None:
        from vieneu import Vieneu
        logger.info(f"Loading VieNeu-TTS model (mode={config.VIENEU_MODE}; cached afterwards)...")
        _TTS = Vieneu(mode=config.VIENEU_MODE)
        try:
            _PRESET_VOICES = list(_TTS.list_preset_voices())
            logger.info(f"VieNeu loaded. {len(_PRESET_VOICES)} preset voices available.")
        except Exception as e:
            logger.warning(f"Could not list preset voices: {e}")
    return _TTS


def _resolve_voice(tts, voice_id: str | None) -> dict:
    """Map voice_id to a VieNeu infer() kwarg.

    - existing .wav path  → {'ref_audio': path}  (zero-shot cloning)
    - non-empty string    → {'voice': name}      (preset voice)
    - empty/None          → {} or configured default preset
    """
    if voice_id and voice_id.lower().endswith(".wav") and os.path.exists(voice_id):
        logger.info(f"Cloning voice from reference audio: {voice_id}")
        return {"ref_audio": voice_id}

    preset = voice_id or config.VIETNAMESE_PRESET_VOICE
    if preset:
        # VieNeu keys preset voices by a short id (e.g. "Vinh"), but exposes a
        # friendly description (e.g. "Xuân Vĩnh (nam miền Nam)"). Accept either:
        # if `preset` matches a description, swap in its short key.
        key = preset
        for description, voice_key in tts.list_preset_voices():
            if preset in (voice_key, description):
                key = voice_key
                break
        # infer() expects the resolved voice dict ({'codes','text'}), not the name.
        try:
            return {"voice": tts.get_preset_voice(key)}
        except Exception as e:
            logger.warning(f"Preset voice '{preset}' not found ({e}); using default voice.")

    # No voice specified — let VieNeu use its built-in default voice.
    return {}


def synthesize_segment_vi(
    text_vi: str,
    output_path: str,
    target_duration: float | None = None,
    voice_id: str | None = None,
) -> dict:
    """Synthesize Vietnamese text to a WAV file using local VieNeu-TTS.

    Args:
        text_vi: Vietnamese text to speak.
        output_path: Where to save the WAV file.
        target_duration: Unused (timeline fit happens downstream); kept for API parity.
        voice_id: VieNeu preset voice name or path to a reference .wav.

    Returns:
        dict with path, actual_duration, speed_adjusted, rate_applied.
    """
    tts = _get_tts()
    infer_kwargs = _resolve_voice(tts, voice_id)

    logger.info(f"TTS request: {len(text_vi)} chars, voice={infer_kwargs or 'default'}")

    # The GGUF backbone samples until it emits the speech-end token. At a high
    # temperature it occasionally rambles past that token and generates tens of
    # seconds of audio for a short line. Vietnamese tops out ~15 chars/sec, so a
    # clip far longer than the text warrants means EOS was missed — regenerate
    # cooler (lower temperature makes the model commit to EOS).
    sample_rate = getattr(tts, "sample_rate", 24000)
    max_plausible = max(len(text_vi) / 6.0 + 2.0, 4.0)
    audio = None
    for temperature, top_k in ((0.7, 40), (0.5, 30), (0.3, 20)):
        audio = tts.infer(text=text_vi, temperature=temperature, top_k=top_k, **infer_kwargs)
        duration = len(audio) / sample_rate
        if duration <= max_plausible:
            break
        logger.warning(
            f"TTS overran ({duration:.1f}s > {max_plausible:.1f}s plausible) at "
            f"temperature={temperature}; retrying cooler."
        )

    # VieNeu writes WAV directly. Re-export through pydub to guarantee a format
    # the rest of the pipeline (pydub / ffmpeg) reads consistently.
    tmp_path = output_path + ".tmp.wav"
    tts.save(audio, tmp_path)
    seg = AudioSegment.from_file(tmp_path)
    seg.export(output_path, format="wav")
    os.remove(tmp_path)

    actual_duration = len(seg) / 1000.0
    return {
        "path": output_path,
        "actual_duration": round(actual_duration, 3),
        "speed_adjusted": False,
        "rate_applied": "vieneu",
    }
