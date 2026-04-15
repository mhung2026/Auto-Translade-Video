# Video Dubbing Pipeline — Design Document

## Decisions Made During Brainstorming

### Scope & Usage
- **Interface:** CLI only (no web GUI) — `python pipeline.py --url "..." --source-lang en`
- **Usage volume:** Light — ~5-10 videos/month, under 15 min each
- **Error handling:** Run from scratch on failure, no resume logic
- **Post-production:** User imports output (audio + SRT) into CapCut for manual adjustments

### Technology Choices
- **Approach:** Phương án A — Azure Speech (ASR + TTS) + Claude API (Translation)
- **ASR:** Azure Speech Service, continuous recognition, word-level timestamps
- **Translation:** Claude Opus (default), model configurable via `.env`
- **TTS:** Azure TTS Neural voices, SSML with prosody rate for timeline matching
- **All config in `.env`:** API keys, model, voice, region, speed ratio — CLI args override `.env`

---

## Architecture

### Pipeline (Sequential, 7 Steps)

```
Input (URL or local file + source language)
  │
  ├─ Step 1: Download Video ─── yt-dlp
  ├─ Step 2: Extract Audio ──── FFmpeg (16kHz mono WAV)
  ├─ Step 3: ASR ────────────── Azure Speech (continuous recognition)
  ├─ Step 4: Translate ──────── Claude API (Opus, batch segments)
  ├─ Step 5: TTS ────────────── Azure TTS (SSML per segment)
  ├─ Step 6: Merge Audio ────── pydub (timeline sync)
  └─ Step 7: Final Video ────── FFmpeg (optional, --skip-video to skip)
  │
  Output: audio_jp_full.wav + SRT files + segments/ + report.json
```

### Data Flow Between Steps

Each step produces files or data structures consumed by the next:

| Step | Input | Output | Format |
|------|-------|--------|--------|
| 1. Download | URL | video.mp4 | File |
| 2. Extract | video.mp4 | original_audio.wav | WAV 16kHz mono |
| 3. ASR | original_audio.wav | list[Segment] | JSON + SRT |
| 4. Translate | list[Segment] | list[Segment] with text_jp | JSON + SRT |
| 5. TTS | text_jp per segment | seg_XXX.wav files | WAV per segment |
| 6. Merge | seg_XXX.wav + timestamps | audio_jp_full.wav | WAV |
| 7. Video | video.mp4 + audio_jp_full.wav | dubbed_video.mp4 | MP4 (optional) |

### Segment Data Structure

```python
Segment = {
    "id": int,
    "text": str,           # Original text (EN/VI)
    "text_jp": str,         # Japanese translation (added in Step 4)
    "start": float,         # Start time in seconds
    "end": float,           # End time in seconds
    "duration": float       # end - start
}
```

---

## Project Structure

```
video-dubbing/
├── .env                    # All config (API keys, voice, model, region)
├── .env.example            # Template
├── .gitignore
├── requirements.txt
├── config.py               # Load .env, expose constants
├── pipeline.py             # CLI entry point (argparse)
├── src/
│   ├── __init__.py
│   ├── downloader.py       # Step 1: yt-dlp wrapper
│   ├── audio_extractor.py  # Step 2: FFmpeg extract audio
│   ├── transcriber.py      # Step 3: Azure ASR continuous recognition
│   ├── translator.py       # Step 4: Claude API translation
│   ├── synthesizer.py      # Step 5: Azure TTS per segment (SSML)
│   ├── audio_merger.py     # Step 6: pydub merge + timeline sync
│   ├── video_merger.py     # Step 7: FFmpeg merge audio into video
│   ├── srt_generator.py    # JSON segments → SRT files
│   └── utils.py            # Logging setup, path helpers
└── output/                 # Gitignored
    └── {video_id}/
        ├── original_audio.wav
        ├── transcript_original.json
        ├── transcript_original.srt
        ├── transcript_jp.json
        ├── transcript_jp.srt
        ├── audio_jp_full.wav
        ├── segments/seg_001.wav ...
        └── report.json
```

---

## Module Details

### config.py
Load all config from `.env` using `python-dotenv`. Expose as module-level constants.

```
Required .env vars:
  AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, ANTHROPIC_API_KEY

Optional .env vars (with defaults):
  ANTHROPIC_MODEL        = claude-opus-4-20250514
  TTS_VOICE              = ja-JP-KeitaNeural
  TTS_MAX_SPEED_RATIO    = 1.4
  DEFAULT_SOURCE_LANG    = en-US
  AUDIO_SAMPLE_RATE      = 16000
  OUTPUT_DIR             = ./output
```

### downloader.py — Step 1
- `download_video(url: str, output_dir: str) -> str`
- Uses yt-dlp Python binding
- Detects platform from URL
- Skips if input is local file
- Returns path to downloaded video

### audio_extractor.py — Step 2
- `extract_audio(video_path: str, output_path: str) -> str`
- FFmpeg via subprocess: `-vn -ar 16000 -ac 1 -acodec pcm_s16le`
- Validates output exists and has size > 0

### transcriber.py — Step 3
- `transcribe(audio_path: str, language: str) -> list[Segment]`
- Azure Speech continuous recognition
- `request_word_level_timestamps = True`
- Converts ticks to seconds (`offset / 10_000_000`)
- Saves JSON + SRT output

### translator.py — Step 4
- `translate_segments(segments: list, source_lang: str) -> list[Segment]`
- Sends full transcript to Claude for context
- Prompt requests concise, natural Japanese translation
- Adds `text_jp` field to each segment
- For videos > 50 segments: batch 20-30 segments with overlapping context
- Model from `.env` (`ANTHROPIC_MODEL`)

### synthesizer.py — Step 5
- `synthesize_segment(text_jp: str, output_path: str, target_duration: float, voice: str) -> dict`
- Azure TTS with SSML
- Speed adjustment logic:
  - JP audio <= original duration → keep default speed
  - JP audio > original by <= 40% → increase prosody rate
  - JP audio > original by > 40% → keep default, flag in report
- Returns `{"path": str, "actual_duration": float, "speed_adjusted": bool}`

### audio_merger.py — Step 6
- `merge_segments(segments: list, segment_dir: str, output_path: str) -> str`
- Creates silent audio track with total video duration
- Places each segment at its original start time
- Handles overlaps: trim or allow slight overlap (CapCut handles)
- Uses pydub.AudioSegment

### video_merger.py — Step 7 (Optional)
- `merge_video(video_path: str, audio_path: str, output_path: str) -> str`
- FFmpeg: copy video stream, replace audio
- Skipped when `--skip-video` flag is set

### srt_generator.py
- `generate_srt(segments: list, output_path: str, text_field: str) -> str`
- Converts segment timestamps to SRT format (`HH:MM:SS,mmm`)
- Generates both original and JP subtitle files

### pipeline.py — CLI Entry Point
- Uses argparse for CLI arguments
- Arguments: `--url`, `--file`, `--source-lang`, `--voice`, `--skip-video`, `--output-dir`
- CLI args override `.env` defaults
- Runs steps 1-7 sequentially
- Prints progress to stdout
- Generates report.json with statistics

---

## Configuration (.env)

```ini
# Azure Speech Service
AZURE_SPEECH_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AZURE_SPEECH_REGION=japaneast

# Claude API
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_MODEL=claude-opus-4-20250514

# TTS Settings
TTS_VOICE=ja-JP-KeitaNeural
TTS_MAX_SPEED_RATIO=1.4

# General
DEFAULT_SOURCE_LANG=en-US
AUDIO_SAMPLE_RATE=16000
OUTPUT_DIR=./output
```

---

## Dependencies

```
azure-cognitiveservices-speech>=1.40.0
anthropic>=0.42.0
pydub>=0.25.1
srt>=3.5.3
yt-dlp>=2024.0.0
python-dotenv>=1.0.1
```

System requirements: Python 3.11+, FFmpeg installed system-wide.

---

## Cost Estimate (Light usage: 5-10 videos/month, <15 min each)

| Service | Usage | Cost |
|---------|-------|------|
| Azure ASR (F0 Free) | ~1-2.5h/month | Free |
| Azure TTS (F0 Free) | ~50-100K chars/month | Free |
| Claude Opus | ~1-2K tokens/video | ~$0.05-0.10/video |
| **Total** | | **~$0.50-1.00/month** |

---

## Limitations

- Japanese text is typically 20-40% longer than EN/VI when spoken — pipeline adjusts speed up to 40%, beyond that user adjusts in CapCut
- Azure ASR accuracy degrades with noisy audio or overlapping speakers
- Azure ASR Vietnamese quality is moderate (not as strong as English)
- Free tier limits: 5h ASR + 500K chars TTS per month
- No resume on failure — pipeline runs from scratch
