# Video Dubbing Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that downloads a video (YouTube/TikTok), transcribes speech to text (Azure ASR), translates to Japanese (Claude API), synthesizes Japanese audio (Azure TTS), and produces timeline-synced audio + SRT files for CapCut editing.

**Architecture:** Sequential 7-step pipeline. Each step is an independent Python module under `src/`. A single `pipeline.py` CLI entry point orchestrates all steps. All config loaded from `.env` via `config.py`.

**Tech Stack:** Python 3.11+, yt-dlp, FFmpeg (subprocess), azure-cognitiveservices-speech, anthropic SDK, pydub, srt, python-dotenv, argparse.

**Spec:** `docs/superpowers/specs/2026-04-15-video-dubbing-pipeline-design.md`
**Original Spec:** `video-dubbing-spec.md`

---

## File Structure

```
video-dubbing/
├── .env.example                # Template for .env
├── .gitignore                  # Ignore .env, output/, __pycache__, *.pyc
├── requirements.txt            # All Python dependencies
├── config.py                   # Load .env, expose constants
├── pipeline.py                 # CLI entry point (argparse), orchestrates all steps
├── src/
│   ├── __init__.py             # Empty init
│   ├── downloader.py           # Step 1: yt-dlp download
│   ├── audio_extractor.py      # Step 2: FFmpeg extract audio
│   ├── transcriber.py          # Step 3: Azure ASR
│   ├── translator.py           # Step 4: Claude API translation
│   ├── synthesizer.py          # Step 5: Azure TTS per segment
│   ├── audio_merger.py         # Step 6: pydub merge + timeline
│   ├── video_merger.py         # Step 7: FFmpeg merge video+audio
│   ├── srt_generator.py        # JSON → SRT conversion
│   └── utils.py                # Logging setup, ensure_dir, format_time
└── tests/
    ├── __init__.py
    ├── test_utils.py
    ├── test_srt_generator.py
    ├── test_audio_merger.py
    ├── test_translator.py
    └── test_config.py
```

---

### Task 1: Project Scaffolding & Config

**Files:**
- Create: `.env.example`
- Create: `.gitignore`
- Create: `requirements.txt`
- Create: `config.py`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
.env
output/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.venv/
venv/
*.wav
*.mp4
*.mkv
*.webm
```

- [ ] **Step 2: Create `requirements.txt`**

```
azure-cognitiveservices-speech>=1.40.0
anthropic>=0.42.0
pydub>=0.25.1
srt>=3.5.3
yt-dlp>=2024.0.0
python-dotenv>=1.0.1
pytest>=8.0.0
```

- [ ] **Step 3: Create `.env.example`**

```ini
# Azure Speech Service
AZURE_SPEECH_KEY=your_azure_speech_key_here
AZURE_SPEECH_REGION=japaneast

# Claude API
ANTHROPIC_API_KEY=sk-ant-your_key_here
ANTHROPIC_MODEL=claude-opus-4-20250514

# TTS Settings
TTS_VOICE=ja-JP-KeitaNeural
TTS_MAX_SPEED_RATIO=1.4

# General
DEFAULT_SOURCE_LANG=en-US
AUDIO_SAMPLE_RATE=16000
OUTPUT_DIR=./output
```

- [ ] **Step 4: Create `src/__init__.py` and `tests/__init__.py`**

Both files are empty — just needed so Python treats the directories as packages.

- [ ] **Step 5: Write failing test for config**

```python
# tests/test_config.py
import os
import pytest


def test_config_loads_env_vars(monkeypatch):
    """config module should expose constants from env vars."""
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "japaneast")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-20250514")
    monkeypatch.setenv("TTS_VOICE", "ja-JP-KeitaNeural")
    monkeypatch.setenv("TTS_MAX_SPEED_RATIO", "1.4")
    monkeypatch.setenv("DEFAULT_SOURCE_LANG", "en-US")
    monkeypatch.setenv("AUDIO_SAMPLE_RATE", "16000")
    monkeypatch.setenv("OUTPUT_DIR", "./output")

    # Force reimport to pick up monkeypatched env
    import importlib
    import config
    importlib.reload(config)

    assert config.AZURE_SPEECH_KEY == "test-key"
    assert config.AZURE_SPEECH_REGION == "japaneast"
    assert config.ANTHROPIC_API_KEY == "sk-ant-test"
    assert config.ANTHROPIC_MODEL == "claude-opus-4-20250514"
    assert config.TTS_VOICE == "ja-JP-KeitaNeural"
    assert config.TTS_MAX_SPEED_RATIO == 1.4
    assert config.DEFAULT_SOURCE_LANG == "en-US"
    assert config.AUDIO_SAMPLE_RATE == 16000
    assert config.OUTPUT_DIR == "./output"


def test_config_defaults(monkeypatch):
    """config should have sensible defaults when optional vars are missing."""
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "japaneast")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    # Clear optional vars
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("TTS_MAX_SPEED_RATIO", raising=False)
    monkeypatch.delenv("DEFAULT_SOURCE_LANG", raising=False)
    monkeypatch.delenv("AUDIO_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    import importlib
    import config
    importlib.reload(config)

    assert config.ANTHROPIC_MODEL == "claude-opus-4-20250514"
    assert config.TTS_VOICE == "ja-JP-KeitaNeural"
    assert config.TTS_MAX_SPEED_RATIO == 1.4
    assert config.DEFAULT_SOURCE_LANG == "en-US"
    assert config.AUDIO_SAMPLE_RATE == 16000
    assert config.OUTPUT_DIR == "./output"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd e:/Program/video_project && python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 7: Implement `config.py`**

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Required
AZURE_SPEECH_KEY = os.environ["AZURE_SPEECH_KEY"]
AZURE_SPEECH_REGION = os.environ["AZURE_SPEECH_REGION"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Optional with defaults
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-20250514")
TTS_VOICE = os.getenv("TTS_VOICE", "ja-JP-KeitaNeural")
TTS_MAX_SPEED_RATIO = float(os.getenv("TTS_MAX_SPEED_RATIO", "1.4"))
DEFAULT_SOURCE_LANG = os.getenv("DEFAULT_SOURCE_LANG", "en-US")
AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd e:/Program/video_project && python -m pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Commit**

```bash
cd e:/Program/video_project
git init
git add .gitignore .env.example requirements.txt config.py src/__init__.py tests/__init__.py tests/test_config.py
git commit -m "feat: project scaffolding with config module"
```

---

### Task 2: Utilities Module

**Files:**
- Create: `src/utils.py`
- Create: `tests/test_utils.py`

- [ ] **Step 1: Write failing tests for utils**

```python
# tests/test_utils.py
import os
import logging
from src.utils import setup_logging, ensure_dir, format_timestamp


def test_setup_logging_returns_logger():
    logger = setup_logging("test_logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger"


def test_ensure_dir_creates_directory(tmp_path):
    new_dir = tmp_path / "subdir" / "nested"
    result = ensure_dir(str(new_dir))
    assert os.path.isdir(result)
    assert result == str(new_dir)


def test_ensure_dir_existing_directory(tmp_path):
    result = ensure_dir(str(tmp_path))
    assert os.path.isdir(result)


def test_format_timestamp_zero():
    assert format_timestamp(0.0) == "00:00:00,000"


def test_format_timestamp_seconds():
    assert format_timestamp(3.2) == "00:00:03,200"


def test_format_timestamp_minutes():
    assert format_timestamp(65.5) == "00:01:05,500"


def test_format_timestamp_hours():
    assert format_timestamp(3661.123) == "01:01:01,123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e:/Program/video_project && python -m pytest tests/test_utils.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `src/utils.py`**

```python
# src/utils.py
import os
import logging


def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger with console handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
    return logger


def ensure_dir(path: str) -> str:
    """Create directory if it doesn't exist, return the path."""
    os.makedirs(path, exist_ok=True)
    return path


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd e:/Program/video_project && python -m pytest tests/test_utils.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/utils.py tests/test_utils.py
git commit -m "feat: add utils module with logging, ensure_dir, format_timestamp"
```

---

### Task 3: SRT Generator

**Files:**
- Create: `src/srt_generator.py`
- Create: `tests/test_srt_generator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_srt_generator.py
import os
from src.srt_generator import generate_srt


def test_generate_srt_original_text(tmp_path):
    segments = [
        {"id": 1, "text": "Hello everyone", "start": 0.5, "end": 3.2, "duration": 2.7},
        {"id": 2, "text": "Welcome to the lesson", "start": 3.5, "end": 6.8, "duration": 3.3},
    ]
    output_path = str(tmp_path / "test.srt")
    result = generate_srt(segments, output_path, text_field="text")

    assert os.path.exists(result)
    content = open(result, encoding="utf-8").read()
    assert "1\n00:00:00,500 --> 00:00:03,200\nHello everyone" in content
    assert "2\n00:00:03,500 --> 00:00:06,800\nWelcome to the lesson" in content


def test_generate_srt_japanese_text(tmp_path):
    segments = [
        {
            "id": 1,
            "text": "Hello",
            "text_jp": "こんにちは",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
        },
    ]
    output_path = str(tmp_path / "test_jp.srt")
    result = generate_srt(segments, output_path, text_field="text_jp")

    content = open(result, encoding="utf-8").read()
    assert "こんにちは" in content


def test_generate_srt_empty_segments(tmp_path):
    output_path = str(tmp_path / "empty.srt")
    result = generate_srt([], output_path, text_field="text")
    content = open(result, encoding="utf-8").read()
    assert content.strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e:/Program/video_project && python -m pytest tests/test_srt_generator.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `src/srt_generator.py`**

```python
# src/srt_generator.py
from src.utils import format_timestamp, setup_logging

logger = setup_logging("srt_generator")


def generate_srt(segments: list[dict], output_path: str, text_field: str = "text") -> str:
    """Generate an SRT subtitle file from segments.

    Args:
        segments: List of segment dicts with 'id', 'start', 'end', and text_field.
        output_path: Path to write the .srt file.
        text_field: Key to use for subtitle text ('text' or 'text_jp').

    Returns:
        The output_path.
    """
    lines = []
    for i, seg in enumerate(segments, start=1):
        start_ts = format_timestamp(seg["start"])
        end_ts = format_timestamp(seg["end"])
        text = seg[text_field]
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"SRT written: {output_path} ({len(segments)} entries)")
    return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd e:/Program/video_project && python -m pytest tests/test_srt_generator.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/srt_generator.py tests/test_srt_generator.py
git commit -m "feat: add SRT generator module"
```

---

### Task 4: Downloader (yt-dlp)

**Files:**
- Create: `src/downloader.py`

- [ ] **Step 1: Implement `src/downloader.py`**

```python
# src/downloader.py
import os
import yt_dlp
from src.utils import setup_logging, ensure_dir

logger = setup_logging("downloader")


def download_video(url: str, output_dir: str) -> str:
    """Download video from URL using yt-dlp.

    Args:
        url: YouTube/TikTok URL.
        output_dir: Directory to save the downloaded video.

    Returns:
        Path to the downloaded video file.

    Raises:
        ValueError: If URL is empty.
        RuntimeError: If download fails.
    """
    if not url:
        raise ValueError("URL cannot be empty")

    ensure_dir(output_dir)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
    }

    logger.info(f"Downloading video from: {url}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "video")
        ext = info.get("ext", "mp4")
        filepath = os.path.join(output_dir, f"{video_id}.{ext}")

        if not os.path.exists(filepath):
            # yt-dlp may use a different extension after merge
            for f in os.listdir(output_dir):
                if f.startswith(video_id):
                    filepath = os.path.join(output_dir, f)
                    break

    if not os.path.exists(filepath):
        raise RuntimeError(f"Download failed: file not found at {filepath}")

    logger.info(f"Downloaded: {filepath}")
    return filepath


def get_video_id(url: str) -> str:
    """Extract video ID from URL without downloading."""
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return info.get("id", "video")
```

Note: No unit test for downloader — it requires network access and a real URL. Will be tested via integration in the full pipeline.

- [ ] **Step 2: Commit**

```bash
git add src/downloader.py
git commit -m "feat: add video downloader module (yt-dlp)"
```

---

### Task 5: Audio Extractor (FFmpeg)

**Files:**
- Create: `src/audio_extractor.py`

- [ ] **Step 1: Implement `src/audio_extractor.py`**

```python
# src/audio_extractor.py
import os
import subprocess
import config
from src.utils import setup_logging

logger = setup_logging("audio_extractor")


def extract_audio(video_path: str, output_path: str) -> str:
    """Extract audio from video file using FFmpeg.

    Converts to WAV format: mono, 16kHz, PCM 16-bit (optimal for ASR).

    Args:
        video_path: Path to the input video file.
        output_path: Path for the output WAV file.

    Returns:
        The output_path.

    Raises:
        FileNotFoundError: If video_path doesn't exist.
        RuntimeError: If FFmpeg fails.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    sample_rate = str(config.AUDIO_SAMPLE_RATE)

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",                    # No video
        "-ar", sample_rate,       # Sample rate
        "-ac", "1",               # Mono
        "-acodec", "pcm_s16le",   # PCM 16-bit
        "-y",                     # Overwrite
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
```

- [ ] **Step 2: Commit**

```bash
git add src/audio_extractor.py
git commit -m "feat: add audio extractor module (FFmpeg)"
```

---

### Task 6: Transcriber (Azure ASR)

**Files:**
- Create: `src/transcriber.py`

- [ ] **Step 1: Implement `src/transcriber.py`**

```python
# src/transcriber.py
import json
import time
import azure.cognitiveservices.speech as speechsdk
import config
from src.utils import setup_logging

logger = setup_logging("transcriber")


def transcribe(audio_path: str, language: str) -> list[dict]:
    """Transcribe audio file using Azure Speech Service.

    Uses continuous recognition to handle long audio files.
    Returns segments with word-level timestamps.

    Args:
        audio_path: Path to WAV file (16kHz mono).
        language: Language code, e.g. 'en-US' or 'vi-VN'.

    Returns:
        List of segment dicts: [{"id", "text", "start", "end", "duration"}, ...]
    """
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

    def on_recognized(evt):
        nonlocal segment_id
        result = evt.result
        if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text.strip():
            # offset and duration are in ticks (100-nanosecond units)
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
        logger.warning(f"Recognition canceled: {evt.cancellation_details.reason}")
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
    logger.info(f"Transcription complete: {len(segments)} segments")

    return segments


def save_transcript(segments: list[dict], output_path: str) -> str:
    """Save segments to JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    logger.info(f"Transcript saved: {output_path}")
    return output_path
```

- [ ] **Step 2: Commit**

```bash
git add src/transcriber.py
git commit -m "feat: add transcriber module (Azure ASR)"
```

---

### Task 7: Translator (Claude API)

**Files:**
- Create: `src/translator.py`
- Create: `tests/test_translator.py`

- [ ] **Step 1: Write failing test for batch splitting logic**

```python
# tests/test_translator.py
from src.translator import _split_into_batches


def test_split_small_list():
    """Less than batch_size items should produce one batch."""
    segments = [{"id": i} for i in range(5)]
    batches = _split_into_batches(segments, batch_size=30)
    assert len(batches) == 1
    assert len(batches[0]) == 5


def test_split_exact_batch_size():
    segments = [{"id": i} for i in range(30)]
    batches = _split_into_batches(segments, batch_size=30)
    assert len(batches) == 1


def test_split_multiple_batches():
    segments = [{"id": i} for i in range(50)]
    batches = _split_into_batches(segments, batch_size=20)
    assert len(batches) == 3
    assert len(batches[0]) == 20
    assert len(batches[1]) == 20
    assert len(batches[2]) == 10


def test_split_empty_list():
    batches = _split_into_batches([], batch_size=20)
    assert len(batches) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e:/Program/video_project && python -m pytest tests/test_translator.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `src/translator.py`**

```python
# src/translator.py
import json
import anthropic
import config
from src.utils import setup_logging

logger = setup_logging("translator")

LANG_NAMES = {
    "en-US": "English",
    "en": "English",
    "vi-VN": "Vietnamese",
    "vi": "Vietnamese",
}


def _split_into_batches(segments: list[dict], batch_size: int = 25) -> list[list[dict]]:
    """Split segments into batches for API calls."""
    if not segments:
        return []
    batches = []
    for i in range(0, len(segments), batch_size):
        batches.append(segments[i : i + batch_size])
    return batches


def _build_prompt(segments: list[dict], source_lang: str) -> str:
    """Build the translation prompt for Claude."""
    lang_name = LANG_NAMES.get(source_lang, source_lang)
    segments_json = json.dumps(
        [{"id": s["id"], "text": s["text"]} for s in segments],
        ensure_ascii=False,
        indent=2,
    )
    return f"""You are a professional translator from {lang_name} to Japanese.
Below is a transcript from a video, split into segments.

REQUIREMENTS:
- Translate each segment into natural, concise Japanese
- Keep translations roughly similar in length to the original (they will be spoken aloud)
- Preserve technical terms accurately
- Return ONLY a JSON array with format: [{{"id": 1, "text_jp": "..."}}]
- Do not include any explanation, markdown, or extra text — only the JSON array

SEGMENTS:
{segments_json}"""


def translate_segments(segments: list[dict], source_lang: str) -> list[dict]:
    """Translate segments from source language to Japanese using Claude API.

    Sends full transcript for context. For >50 segments, splits into batches
    with overlapping context.

    Args:
        segments: List of segment dicts with 'id' and 'text'.
        source_lang: Source language code (e.g., 'en-US', 'vi-VN').

    Returns:
        The same segments list with 'text_jp' added to each dict.
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    batches = _split_into_batches(segments, batch_size=25)

    logger.info(
        f"Translating {len(segments)} segments in {len(batches)} batch(es) "
        f"using model {config.ANTHROPIC_MODEL}"
    )

    translations = {}  # id -> text_jp

    for batch_idx, batch in enumerate(batches):
        logger.info(f"Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} segments)")

        prompt = _build_prompt(batch, source_lang)

        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        translated = json.loads(response_text)

        for item in translated:
            translations[item["id"]] = item["text_jp"]

    # Merge translations back into segments
    for seg in segments:
        if seg["id"] in translations:
            seg["text_jp"] = translations[seg["id"]]
        else:
            logger.warning(f"Missing translation for segment {seg['id']}")
            seg["text_jp"] = seg["text"]  # Fallback to original

    logger.info(f"Translation complete: {len(translations)}/{len(segments)} segments translated")
    return segments
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd e:/Program/video_project && python -m pytest tests/test_translator.py -v`
Expected: PASS (4 tests — only the batch splitting logic is tested without API calls)

- [ ] **Step 5: Commit**

```bash
git add src/translator.py tests/test_translator.py
git commit -m "feat: add translator module (Claude API)"
```

---

### Task 8: Synthesizer (Azure TTS)

**Files:**
- Create: `src/synthesizer.py`

- [ ] **Step 1: Implement `src/synthesizer.py`**

```python
# src/synthesizer.py
import os
import azure.cognitiveservices.speech as speechsdk
from pydub import AudioSegment
import config
from src.utils import setup_logging

logger = setup_logging("synthesizer")


def _build_ssml(text: str, voice: str, rate: str = "+0%") -> str:
    """Build SSML string for Azure TTS."""
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
    """Synthesize Japanese text to speech using Azure TTS.

    If target_duration is provided, adjusts speech rate to approximately
    match the original segment duration.

    Args:
        text_jp: Japanese text to synthesize.
        output_path: Path to save the WAV file.
        target_duration: Target duration in seconds (from original segment).
        voice: Voice name (defaults to config.TTS_VOICE).

    Returns:
        Dict with 'path', 'actual_duration', 'speed_adjusted'.
    """
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

    # First pass: synthesize at default speed
    ssml = _build_ssml(text_jp, voice)
    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(f"TTS failed: {details.reason} — {details.error_details}")

    # Measure actual duration
    audio = AudioSegment.from_wav(output_path)
    actual_duration = len(audio) / 1000.0  # ms to seconds
    speed_adjusted = False

    # Adjust speed if needed
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
```

- [ ] **Step 2: Commit**

```bash
git add src/synthesizer.py
git commit -m "feat: add synthesizer module (Azure TTS with speed adjustment)"
```

---

### Task 9: Audio Merger (pydub)

**Files:**
- Create: `src/audio_merger.py`
- Create: `tests/test_audio_merger.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_audio_merger.py
import os
from pydub import AudioSegment
from pydub.generators import Sine
from src.audio_merger import merge_segments


def _make_segment_file(path: str, duration_ms: int = 1000):
    """Create a short WAV file for testing."""
    tone = Sine(440).to_audio_segment(duration=duration_ms)
    tone.export(path, format="wav")


def test_merge_segments_basic(tmp_path):
    seg_dir = str(tmp_path / "segments")
    os.makedirs(seg_dir)

    # Create 2 fake segment files
    _make_segment_file(os.path.join(seg_dir, "seg_001.wav"), 500)
    _make_segment_file(os.path.join(seg_dir, "seg_002.wav"), 800)

    segments = [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0},
        {"id": 2, "start": 2.0, "end": 3.5, "duration": 1.5},
    ]
    total_duration = 5.0
    output_path = str(tmp_path / "merged.wav")

    result = merge_segments(segments, seg_dir, output_path, total_duration)
    assert os.path.exists(result)

    audio = AudioSegment.from_wav(result)
    # Should be approximately total_duration seconds
    assert abs(len(audio) / 1000.0 - total_duration) < 0.1


def test_merge_segments_empty(tmp_path):
    seg_dir = str(tmp_path / "segments")
    os.makedirs(seg_dir)
    output_path = str(tmp_path / "merged.wav")

    result = merge_segments([], seg_dir, output_path, total_duration=3.0)
    assert os.path.exists(result)
    audio = AudioSegment.from_wav(result)
    assert abs(len(audio) / 1000.0 - 3.0) < 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e:/Program/video_project && python -m pytest tests/test_audio_merger.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement `src/audio_merger.py`**

```python
# src/audio_merger.py
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
    """Merge individual segment audio files into a single timeline-synced WAV.

    Places each segment at its original start time, filling gaps with silence.

    Args:
        segments: List of segment dicts with 'id', 'start', 'end'.
        segment_dir: Directory containing seg_001.wav, seg_002.wav, etc.
        output_path: Path for the merged output WAV.
        total_duration: Total duration of the original video in seconds.

    Returns:
        The output_path.
    """
    # Create a silent audio track of the total video duration
    total_ms = int(total_duration * 1000)
    merged = AudioSegment.silent(duration=total_ms)

    for seg in segments:
        seg_file = os.path.join(segment_dir, f"seg_{seg['id']:03d}.wav")
        if not os.path.exists(seg_file):
            logger.warning(f"Segment file not found: {seg_file}, skipping")
            continue

        segment_audio = AudioSegment.from_wav(seg_file)
        start_ms = int(seg["start"] * 1000)

        # Overlay the segment at its start position
        merged = merged.overlay(segment_audio, position=start_ms)
        logger.debug(f"Placed segment {seg['id']} at {seg['start']:.1f}s")

    merged.export(output_path, format="wav")
    logger.info(
        f"Audio merged: {output_path} ({len(segments)} segments, {total_duration:.1f}s)"
    )
    return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd e:/Program/video_project && python -m pytest tests/test_audio_merger.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/audio_merger.py tests/test_audio_merger.py
git commit -m "feat: add audio merger module (pydub timeline sync)"
```

---

### Task 10: Video Merger (FFmpeg)

**Files:**
- Create: `src/video_merger.py`

- [ ] **Step 1: Implement `src/video_merger.py`**

```python
# src/video_merger.py
import os
import subprocess
from src.utils import setup_logging

logger = setup_logging("video_merger")


def merge_video(video_path: str, audio_path: str, output_path: str) -> str:
    """Merge Japanese audio into original video, replacing the original audio.

    Uses FFmpeg to copy the video stream and replace the audio stream.

    Args:
        video_path: Path to the original video file.
        audio_path: Path to the Japanese audio WAV file.
        output_path: Path for the output video file.

    Returns:
        The output_path.

    Raises:
        FileNotFoundError: If video or audio file doesn't exist.
        RuntimeError: If FFmpeg fails.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-map", "0:v",
        "-map", "1:a",
        "-y",
        output_path,
    ]

    logger.info(f"Merging video + audio → {output_path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")

    logger.info(f"Video merged: {output_path}")
    return output_path
```

- [ ] **Step 2: Commit**

```bash
git add src/video_merger.py
git commit -m "feat: add video merger module (FFmpeg)"
```

---

### Task 11: Pipeline CLI Entry Point

**Files:**
- Create: `pipeline.py`

- [ ] **Step 1: Implement `pipeline.py`**

```python
# pipeline.py
"""Video Dubbing Pipeline — CLI Entry Point.

Usage:
    python pipeline.py --url "https://youtube.com/watch?v=xxx" --source-lang en
    python pipeline.py --file video.mp4 --source-lang vi
    python pipeline.py --url "..." --source-lang en --voice ja-JP-NanamiNeural --skip-video
"""
import argparse
import json
import os
import sys
import time

import config
from src.utils import setup_logging, ensure_dir
from src.downloader import download_video, get_video_id
from src.audio_extractor import extract_audio
from src.transcriber import transcribe, save_transcript
from src.translator import translate_segments
from src.synthesizer import synthesize_segment
from src.audio_merger import merge_segments
from src.video_merger import merge_video
from src.srt_generator import generate_srt

logger = setup_logging("pipeline")

# Map short lang codes to Azure Speech language codes
LANG_MAP = {
    "en": "en-US",
    "vi": "vi-VN",
    "en-US": "en-US",
    "vi-VN": "vi-VN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Video Dubbing Pipeline: EN/VI → JP")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="YouTube/TikTok video URL")
    group.add_argument("--file", help="Local video file path")

    parser.add_argument(
        "--source-lang",
        default=config.DEFAULT_SOURCE_LANG,
        help=f"Source language: en, vi, en-US, vi-VN (default: {config.DEFAULT_SOURCE_LANG})",
    )
    parser.add_argument(
        "--voice",
        default=config.TTS_VOICE,
        help=f"TTS voice name (default: {config.TTS_VOICE})",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip final video merge (only produce audio + SRT)",
    )
    parser.add_argument(
        "--output-dir",
        default=config.OUTPUT_DIR,
        help=f"Output directory (default: {config.OUTPUT_DIR})",
    )
    return parser.parse_args()


def run_pipeline(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice: str,
    skip_video: bool,
    output_dir: str,
) -> dict:
    """Run the full dubbing pipeline."""
    start_time = time.time()

    # Resolve language code
    lang_code = LANG_MAP.get(source_lang, source_lang)
    logger.info(f"Source language: {lang_code}")

    # --- Step 1: Download or use local file ---
    logger.info("=" * 60)
    logger.info("STEP 1: Acquiring video")
    if url:
        video_id = get_video_id(url)
        work_dir = ensure_dir(os.path.join(output_dir, video_id))
        video_path = download_video(url, work_dir)
    else:
        video_path = file_path
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        video_id = os.path.splitext(os.path.basename(video_path))[0]
        work_dir = ensure_dir(os.path.join(output_dir, video_id))
    logger.info(f"Video: {video_path}")

    # --- Step 2: Extract audio ---
    logger.info("=" * 60)
    logger.info("STEP 2: Extracting audio")
    audio_path = os.path.join(work_dir, "original_audio.wav")
    extract_audio(video_path, audio_path)

    # --- Step 3: Speech-to-Text (ASR) ---
    logger.info("=" * 60)
    logger.info("STEP 3: Transcribing audio (ASR)")
    segments = transcribe(audio_path, lang_code)
    save_transcript(segments, os.path.join(work_dir, "transcript_original.json"))
    generate_srt(segments, os.path.join(work_dir, "transcript_original.srt"), text_field="text")
    logger.info(f"Transcribed {len(segments)} segments")

    # --- Step 4: Translate to Japanese ---
    logger.info("=" * 60)
    logger.info("STEP 4: Translating to Japanese")
    segments = translate_segments(segments, lang_code)
    save_transcript(segments, os.path.join(work_dir, "transcript_jp.json"))
    generate_srt(segments, os.path.join(work_dir, "transcript_jp.srt"), text_field="text_jp")

    # --- Step 5: TTS for each segment ---
    logger.info("=" * 60)
    logger.info("STEP 5: Synthesizing Japanese audio (TTS)")
    seg_dir = ensure_dir(os.path.join(work_dir, "segments"))
    tts_results = []
    for seg in segments:
        seg_path = os.path.join(seg_dir, f"seg_{seg['id']:03d}.wav")
        result = synthesize_segment(
            text_jp=seg["text_jp"],
            output_path=seg_path,
            target_duration=seg["duration"],
            voice=voice,
        )
        tts_results.append(result)
        logger.info(
            f"  Segment {seg['id']}: {result['actual_duration']:.1f}s "
            f"(target: {seg['duration']:.1f}s, adjusted: {result['speed_adjusted']})"
        )

    # --- Step 6: Merge audio ---
    logger.info("=" * 60)
    logger.info("STEP 6: Merging audio segments")
    # Total duration = end of last segment + small buffer
    total_duration = max(seg["end"] for seg in segments) + 1.0 if segments else 0
    merged_audio_path = os.path.join(work_dir, "audio_jp_full.wav")
    merge_segments(segments, seg_dir, merged_audio_path, total_duration)

    # --- Step 7: Merge video (optional) ---
    dubbed_video_path = None
    if not skip_video:
        logger.info("=" * 60)
        logger.info("STEP 7: Creating dubbed video")
        dubbed_video_path = os.path.join(work_dir, "dubbed_video.mp4")
        merge_video(video_path, merged_audio_path, dubbed_video_path)

    # --- Generate report ---
    elapsed = time.time() - start_time
    report = {
        "video_id": video_id,
        "source_language": lang_code,
        "voice": voice,
        "total_segments": len(segments),
        "total_original_duration": round(sum(s["duration"] for s in segments), 3),
        "total_tts_duration": round(sum(r["actual_duration"] for r in tts_results), 3),
        "segments_speed_adjusted": sum(1 for r in tts_results if r["speed_adjusted"]),
        "processing_time_seconds": round(elapsed, 1),
        "output_dir": work_dir,
        "files": {
            "original_audio": audio_path,
            "transcript_original_json": os.path.join(work_dir, "transcript_original.json"),
            "transcript_original_srt": os.path.join(work_dir, "transcript_original.srt"),
            "transcript_jp_json": os.path.join(work_dir, "transcript_jp.json"),
            "transcript_jp_srt": os.path.join(work_dir, "transcript_jp.srt"),
            "audio_jp_full": merged_audio_path,
            "dubbed_video": dubbed_video_path,
        },
    }

    report_path = os.path.join(work_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Output:    {work_dir}")
    logger.info(f"  Segments:  {report['total_segments']}")
    logger.info(f"  Duration:  {report['total_original_duration']:.1f}s original, "
                f"{report['total_tts_duration']:.1f}s JP audio")
    logger.info(f"  Adjusted:  {report['segments_speed_adjusted']} segments sped up")
    logger.info(f"  Time:      {elapsed:.1f}s")
    logger.info("=" * 60)

    return report


def main():
    args = parse_args()
    try:
        run_pipeline(
            url=args.url,
            file_path=args.file,
            source_lang=args.source_lang,
            voice=args.voice,
            skip_video=args.skip_video,
            output_dir=args.output_dir,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add pipeline.py
git commit -m "feat: add pipeline CLI entry point with full 7-step orchestration"
```

---

### Task 12: Final Integration — Install, Verify, and Run All Tests

- [ ] **Step 1: Install dependencies**

```bash
cd e:/Program/video_project
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt
```

- [ ] **Step 2: Create `.env` from `.env.example`**

Copy `.env.example` to `.env` and fill in real API keys.

- [ ] **Step 3: Run all unit tests**

```bash
cd e:/Program/video_project
python -m pytest tests/ -v
```

Expected: All tests pass (test_config, test_utils, test_srt_generator, test_translator, test_audio_merger).

- [ ] **Step 4: Verify CLI help works**

```bash
python pipeline.py --help
```

Expected: Shows usage with all arguments (--url, --file, --source-lang, --voice, --skip-video, --output-dir).

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete video dubbing pipeline v1.0"
```
