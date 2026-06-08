import os
import sys
from dotenv import load_dotenv

load_dotenv()

def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        print(f"ERROR: Required environment variable '{key}' is not set.", file=sys.stderr)
        print(f"Please copy .env.example to .env and fill in your API keys.", file=sys.stderr)
        sys.exit(1)
    return value

# Azure Speech — optional now. The Vietnamese pipeline uses local WhisperX for ASR
# and local VieNeu-TTS for synthesis, so no key is needed. These are only required
# by the Japanese pipeline (pipeline.py), which still calls Azure.
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "")

# WhisperX ASR (local) — replaces Azure for the Vietnamese pipeline.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# VieNeu-TTS (local) — replaces LucyLab for the Vietnamese pipeline.
# A voice id can be either a VieNeu preset voice name or a path to a 3-5s
# reference .wav for zero-shot cloning.
# Mode: 'standard' uses a GGUF backbone via llama.cpp (CPU, reliable EOS).
# 'v3turbo' is the torch-free ONNX engine but currently loops on short text.
VIENEU_MODE = os.getenv("VIENEU_MODE", "standard")
VIETNAMESE_PRESET_VOICE = os.getenv("VIETNAMESE_PRESET_VOICE", "")

# Optional with defaults
TTS_VOICE = os.getenv("TTS_VOICE", "ja-JP-KeitaNeural")
TTS_MAX_SPEED_RATIO = float(os.getenv("TTS_MAX_SPEED_RATIO", "1.3"))
DEFAULT_SOURCE_LANG = os.getenv("DEFAULT_SOURCE_LANG", "en-US")
AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
# Vietnamese TTS (LucyLab API)
VIETNAMESE_API_KEY = os.getenv("VIETNAMESE_API_KEY", "")
VIETNAMESE_VOICEID_MALE = os.getenv("VIETNAMESE_VOICEID_MALE", "")
VIETNAMESE_VOICEID_FEMALE = os.getenv("VIETNAMESE_VOICEID_FEMALE", "")
LUCYLAB_API_URL = os.getenv("LUCYLAB_API_URL", "https://api.lucylab.io/json-rpc")
VIETNAMESE_TTS_MAX_SPEED = float(os.getenv("VIETNAMESE_TTS_MAX_SPEED", "1.3"))
# Slow down factor for Vietnamese audio (0.82 = 18% slower, 1.0 = no change)
AUDIO_SLOW_FACTOR = float(os.getenv("AUDIO_SLOW_FACTOR", "0.82"))
VIETNAMESE_OUTPUT_DIR = os.getenv("VIETNAMESE_OUTPUT_DIR", "")
VOICE_TYPE = os.getenv("VOICE_TYPE", os.getenv("Voice_type", "")).strip().lower()

VIETNAMESE_VIDEO_URL = os.getenv("VIETNAMESE_VIDEO_URL", os.getenv("Vietnamese_video_url", ""))

VIDEO_URL = os.getenv("VIDEO_URL", "")

# Google Gemini API (thumbnails + content generation)
GOOGLE_API_KEY = os.getenv("google_api_key", os.getenv("GOOGLE_API_KEY", ""))
IMAGE_MODEL_ID = os.getenv("image_model_id", "gemini-2.0-flash-exp")
CONTENT_MODEL_ID = os.getenv("content_model_id", "gemini-2.0-flash")
