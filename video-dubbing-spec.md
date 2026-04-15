# Video Dubbing Pipeline — Project Specification

## 1. Tổng quan dự án

### Mục tiêu
Xây dựng công cụ tự động chuyển đổi video tiếng Anh/Việt sang tiếng Nhật, bao gồm: nhận dạng giọng nói (ASR), dịch thuật AI, và tổng hợp giọng nói (TTS). Output là file audio tiếng Nhật có timeline tương đối khớp với video gốc, kèm file subtitle SRT để người dùng chỉnh sửa thủ công trong phần mềm edit video (CapCut).

### Input
- URL video từ YouTube hoặc TikTok
- Hoặc file video local (.mp4, .mkv, .webm)
- Ngôn ngữ nguồn: Tiếng Anh (en) hoặc Tiếng Việt (vi)

### Output
```
output/{video_id}/
├── original_audio.wav          # Audio gốc trích từ video
├── transcript_original.json    # Transcript ngôn ngữ gốc với timestamps
├── transcript_original.srt     # Subtitle ngôn ngữ gốc (dùng trong CapCut)
├── transcript_jp.json          # Transcript tiếng Nhật với timestamps
├── transcript_jp.srt           # Subtitle tiếng Nhật (dùng trong CapCut)
├── audio_jp_full.wav           # Audio tiếng Nhật ghép đầy đủ
├── segments/                   # Từng đoạn audio JP riêng lẻ
│   ├── seg_001.wav
│   ├── seg_002.wav
│   └── ...
└── report.json                 # Báo cáo: số segment, duration so sánh, v.v.
```

---

## 2. Kiến trúc Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INPUT                               │
│         YouTube/TikTok URL  hoặc  Local Video File              │
│         + Source Language (en / vi)                              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: DOWNLOAD VIDEO                                        │
│  Tool: yt-dlp                                                   │
│  - Download video từ URL                                        │
│  - Hỗ trợ YouTube, TikTok, và 1000+ sites khác                │
│  - Nếu input là file local thì skip bước này                   │
│  Output: video.mp4                                              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: EXTRACT AUDIO                                         │
│  Tool: FFmpeg                                                   │
│  - Tách audio từ video                                         │
│  - Convert sang WAV 16kHz mono (tối ưu cho ASR)               │
│  - Lệnh: ffmpeg -i video.mp4 -vn -ar 16000 -ac 1 audio.wav   │
│  Output: original_audio.wav                                     │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: SPEECH-TO-TEXT (ASR)                                  │
│  Tool: Azure Speech Service (Continuous Recognition)            │
│  - Nhận dạng giọng nói với word-level timestamps               │
│  - Hỗ trợ tiếng Anh (en-US) và tiếng Việt (vi-VN)            │
│  - Tự động chia thành segments theo câu                        │
│  Output: transcript_original.json + transcript_original.srt    │
│                                                                 │
│  Cấu trúc JSON output:                                        │
│  [                                                              │
│    {                                                            │
│      "id": 1,                                                  │
│      "text": "Hello everyone, welcome to today's lesson",      │
│      "start": 0.5,                                             │
│      "end": 3.2,                                               │
│      "duration": 2.7                                           │
│    },                                                           │
│    ...                                                          │
│  ]                                                              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4: TRANSLATE TO JAPANESE                                  │
│  Tool: Claude API (Opus model)                                  │
│  - Gửi toàn bộ transcript để Claude hiểu ngữ cảnh             │
│  - Dịch từng segment giữ nguyên cấu trúc ID/timestamps        │
│  - Prompt yêu cầu bản dịch ngắn gọn, tự nhiên                 │
│  Output: transcript_jp.json + transcript_jp.srt                │
│                                                                 │
│  Cấu trúc JSON output (bổ sung text_jp):                      │
│  [                                                              │
│    {                                                            │
│      "id": 1,                                                  │
│      "text": "Hello everyone, welcome to today's lesson",      │
│      "text_jp": "皆さん、こんにちは。本日のレッスンへようこそ。",│
│      "start": 0.5,                                             │
│      "end": 3.2,                                               │
│      "duration": 2.7                                           │
│    },                                                           │
│    ...                                                          │
│  ]                                                              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: TEXT-TO-SPEECH (TTS)                                  │
│  Tool: Azure TTS (Neural Voice)                                 │
│  - Tạo audio JP cho từng segment riêng lẻ                     │
│  - Voice mặc định: ja-JP-KeitaNeural                           │
│  - Dùng SSML để kiểm soát tốc độ đọc (prosody rate)           │
│  - Điều chỉnh tốc độ tương đối để gần khớp duration gốc      │
│    + Nếu JP audio ngắn hơn gốc → giữ nguyên                  │
│    + Nếu JP audio dài hơn gốc ≤ 40% → tăng tốc nhẹ           │
│    + Nếu JP audio dài hơn gốc > 40% → giữ nguyên, user tự    │
│      chỉnh trong CapCut                                        │
│  Output: segments/seg_001.wav, seg_002.wav, ...                │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 6: MERGE AUDIO                                           │
│  Tool: pydub (Python) + FFmpeg                                  │
│  - Ghép các segment audio theo timestamps gốc                  │
│  - Chèn silence giữa các segment theo khoảng cách thời gian   │
│  - Tạo file audio JP đầy đủ                                   │
│  Output: audio_jp_full.wav                                      │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 7: GENERATE FINAL VIDEO (Optional)                       │
│  Tool: FFmpeg                                                   │
│  - Ghép audio JP vào video gốc (thay thế audio gốc)           │
│  - Giữ nguyên video stream, chỉ thay audio                    │
│  - Lệnh: ffmpeg -i video.mp4 -i audio_jp.wav                  │
│           -c:v copy -map 0:v -map 1:a output.mp4              │
│  Output: dubbed_video.mp4                                       │
│                                                                 │
│  LƯU Ý: Bước này là optional vì user sẽ chỉnh sửa thủ công  │
│  trong CapCut bằng cách import video gốc + audio JP +          │
│  file SRT subtitle.                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

### Runtime & Language
| Thành phần | Công nghệ | Version |
|---|---|---|
| Runtime | Node.js hoặc Python | Python 3.11+ khuyến nghị |
| Package manager | pip + venv | — |

### Dependencies chính

| Package | Mục đích | Ghi chú |
|---|---|---|
| `yt-dlp` | Download video YouTube/TikTok | CLI tool + Python binding |
| `ffmpeg-python` hoặc `subprocess` | Xử lý audio/video | Cần cài FFmpeg system-wide |
| `azure-cognitiveservices-speech` | ASR + TTS | Azure Speech SDK |
| `anthropic` | Dịch thuật qua Claude API | Claude Opus model |
| `pydub` | Xử lý audio (merge, pad silence, speed) | Cần FFmpeg |
| `srt` | Tạo file SRT subtitle | Lightweight |

### External Services

| Service | Mục đích | Pricing | Credentials |
|---|---|---|---|
| Azure Speech Service | ASR (Speech-to-Text) + TTS (Text-to-Speech) | Free F0: 5h ASR + 500K chars TTS/tháng | Key + Region (japaneast) |
| Claude API (Anthropic) | Dịch thuật EN/VI → JP | ~$15/1M input tokens (Opus) | API Key |

---

## 4. Cấu trúc Project

```
video-dubbing/
├── .env                        # API keys (không commit lên git)
├── .env.example                # Template cho .env
├── .gitignore
├── README.md
├── requirements.txt
├── pyproject.toml              # Project config
│
├── config.py                   # Load config từ .env, constants
│
├── src/
│   ├── __init__.py
│   ├── downloader.py           # [Step 1] Download video (yt-dlp)
│   ├── audio_extractor.py      # [Step 2] Extract audio (FFmpeg)
│   ├── transcriber.py          # [Step 3] ASR + timestamps (Azure Speech)
│   ├── translator.py           # [Step 4] Dịch thuật (Claude API)
│   ├── synthesizer.py          # [Step 5] TTS từng segment (Azure TTS)
│   ├── audio_merger.py         # [Step 6] Merge segments + timeline sync
│   ├── video_merger.py         # [Step 7] Ghép audio vào video (FFmpeg)
│   ├── srt_generator.py        # Tạo file SRT từ transcript JSON
│   └── utils.py                # Helper functions
│
├── pipeline.py                 # Main entry point — chạy toàn bộ pipeline
│
├── output/                     # Output directory (gitignored)
│   └── {video_id}/
│       ├── original_audio.wav
│       ├── transcript_original.json
│       ├── transcript_original.srt
│       ├── transcript_jp.json
│       ├── transcript_jp.srt
│       ├── audio_jp_full.wav
│       ├── segments/
│       └── report.json
│
└── tests/                      # Unit tests
    ├── test_transcriber.py
    ├── test_translator.py
    └── test_synthesizer.py
```

---

## 5. Chi tiết từng Module

### 5.1 config.py — Cấu hình

```
Biến môi trường cần thiết (.env):
- AZURE_SPEECH_KEY          = Key 1 từ Azure Speech resource
- AZURE_SPEECH_REGION       = japaneast
- ANTHROPIC_API_KEY         = Claude API key

Hằng số:
- DEFAULT_VOICE             = ja-JP-KeitaNeural
- DEFAULT_SOURCE_LANG       = en-US
- AUDIO_SAMPLE_RATE         = 16000
- AUDIO_CHANNELS            = 1
- MAX_SPEED_RATIO           = 1.4  (tăng tốc tối đa 40%)
- OUTPUT_AUDIO_FORMAT       = wav
```

### 5.2 downloader.py — Download Video

```
Function: download_video(url: str, output_dir: str) → str (filepath)

Logic:
1. Detect platform (YouTube / TikTok / other) từ URL
2. Gọi yt-dlp với options:
   - Format: best video+audio
   - Output template: {output_dir}/{video_id}.mp4
3. Return đường dẫn file video đã download

Edge cases:
- URL không hợp lệ → raise ValueError
- Video bị private/xóa → raise DownloadError
- Nếu input là file local → skip download, return path trực tiếp
```

### 5.3 audio_extractor.py — Trích xuất Audio

```
Function: extract_audio(video_path: str, output_path: str) → str

Logic:
1. Chạy FFmpeg command:
   ffmpeg -i {video_path} -vn -ar 16000 -ac 1 -acodec pcm_s16le {output_path}
2. Validate output file tồn tại và có size > 0
3. Return output_path

Parameters:
- sample_rate: 16000 (tối ưu cho ASR)
- channels: 1 (mono)
- codec: PCM 16-bit (WAV)
```

### 5.4 transcriber.py — ASR + Timestamps

```
Function: transcribe(audio_path: str, language: str) → list[Segment]

Segment = {
    "id": int,
    "text": str,
    "start": float (seconds),
    "end": float (seconds),
    "duration": float (seconds)
}

Logic:
1. Khởi tạo Azure SpeechRecognizer với:
   - subscription key + region
   - language: "en-US" hoặc "vi-VN"
   - audio input từ file WAV
   - request_word_level_timestamps = True
2. Dùng continuous_recognition để xử lý toàn bộ audio
3. Với mỗi recognized event:
   - Lấy text + offset + duration
   - Convert offset từ ticks sang seconds (offset / 10_000_000)
   - Tạo Segment object
4. Gom các recognition results thành list segments
5. Export ra JSON + SRT

Azure Speech Config quan trọng:
- speech_config.request_word_level_timestamps = True
- speech_config.output_format = speechsdk.OutputFormat.Detailed
- Dùng Continuous Recognition (không phải recognize_once)
  vì video có thể dài nhiều phút
```

### 5.5 translator.py — Dịch thuật

```
Function: translate_segments(segments: list, source_lang: str) → list[Segment]

Logic:
1. Chuẩn bị prompt cho Claude:
   - System prompt: vai trò dịch giả chuyên nghiệp
   - Gửi toàn bộ segments (để Claude hiểu ngữ cảnh)
   - Yêu cầu dịch từng segment, giữ ID mapping
   - Yêu cầu bản dịch ngắn gọn, tự nhiên
2. Gọi Claude API (model: claude-opus-4-20250514)
3. Parse response → thêm field "text_jp" vào mỗi segment
4. Return updated segments

Prompt template:
"""
Bạn là dịch giả chuyên nghiệp {source} → Tiếng Nhật.
Dưới đây là transcript từ một video, đã chia thành segments.

YÊU CẦU:
- Dịch từng segment sang tiếng Nhật tự nhiên
- Giữ bản dịch ngắn gọn, tương đương độ dài bản gốc
- Giữ đúng thuật ngữ chuyên ngành
- Output dạng JSON array với format: [{"id": 1, "text_jp": "..."}, ...]

SEGMENTS:
{json_segments}
"""

Chiến lược cho video dài (> 50 segments):
- Chia thành batches 20-30 segments
- Gửi kèm 2-3 segments cuối của batch trước làm context
- Merge kết quả
```

### 5.6 synthesizer.py — TTS

```
Function: synthesize_segment(text_jp: str, output_path: str,
                              target_duration: float = None,
                              voice: str = "ja-JP-KeitaNeural") → dict

Return: {"path": str, "actual_duration": float, "speed_adjusted": bool}

Logic:
1. Tạo SSML với voice name + text
2. Nếu target_duration được cung cấp:
   a. Trước tiên tạo audio ở tốc độ mặc định
   b. Đo actual_duration
   c. Tính ratio = actual_duration / target_duration
   d. Nếu ratio > 1.0 và ratio <= 1.4:
      - Tạo lại audio với prosody rate = +{(ratio-1)*100}%
   e. Nếu ratio > 1.4:
      - Giữ nguyên tốc độ mặc định (user sẽ chỉnh trong CapCut)
      - Flag trong report
3. Nếu không có target_duration → tạo audio tốc độ mặc định
4. Save file WAV
5. Return metadata

SSML template:
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP">
  <voice name="{voice}">
    <prosody rate="{rate}">
      {text_jp}
    </prosody>
  </voice>
</speak>

Voices khả dụng (đã test trên Azure Speech Studio):
- ja-JP-KeitaNeural    ← Mặc định (nam, casual)
- ja-JP-NanamiNeural   (nữ, sáng, 4 styles)
- ja-JP-DaichiNeural   (nam, trầm, formal)
- ja-JP-NaokiNeural    (nam, professional)
- ja-JP-MayuNeural     (nữ, animated)
- ja-JP-ShioriNeural   (nữ, steady)
- ja-JP-AoiNeural      (nữ, trẻ em)
```

### 5.7 audio_merger.py — Ghép Audio + Timeline

```
Function: merge_segments(segments: list, segment_dir: str,
                          output_path: str) → str

Logic:
1. Tạo audio track rỗng có duration = tổng thời lượng video gốc
2. Với mỗi segment:
   a. Load file audio segment (seg_XXX.wav)
   b. Đặt vào vị trí start time của segment gốc
   c. Nếu audio segment dài hơn khoảng cách đến segment tiếp theo:
      - Cắt bớt hoặc để chồng nhẹ (CapCut sẽ xử lý)
   d. Nếu audio segment ngắn hơn → tự động có silence ở giữa
3. Export ra file WAV đầy đủ
4. Return output_path

Thư viện: pydub.AudioSegment
```

### 5.8 srt_generator.py — Tạo Subtitle SRT

```
Function: generate_srt(segments: list, output_path: str,
                        text_field: str = "text") → str

Logic:
1. Với mỗi segment:
   - Convert start/end seconds → SRT timestamp format (HH:MM:SS,mmm)
   - Tạo SRT entry
2. Write file .srt

Format SRT:
1
00:00:00,500 --> 00:00:03,200
Hello everyone, welcome to today's lesson

2
00:00:03,500 --> 00:00:06,800
Today we will discuss safety procedures

Tạo 2 file:
- transcript_original.srt (text_field = "text")
- transcript_jp.srt (text_field = "text_jp")
```

### 5.9 pipeline.py — Main Entry Point

```
Function: run_pipeline(url_or_path: str, source_lang: str,
                        voice: str = "ja-JP-KeitaNeural") → dict

Logic:
1. Parse arguments (URL vs local file, source language)
2. Tạo output directory: output/{video_id}/
3. Chạy tuần tự:
   Step 1: download_video() → video.mp4
   Step 2: extract_audio() → original_audio.wav
   Step 3: transcribe() → transcript_original.json + .srt
   Step 4: translate_segments() → transcript_jp.json + .srt
   Step 5: synthesize từng segment → segments/seg_XXX.wav
   Step 6: merge_segments() → audio_jp_full.wav
   Step 7: (optional) merge video + audio → dubbed_video.mp4
4. Tạo report.json với thống kê
5. Print summary

CLI arguments:
--url           URL video YouTube/TikTok
--file          Đường dẫn file video local
--source-lang   Ngôn ngữ nguồn: "en" hoặc "vi" (mặc định: en)
--voice         Voice ID cho TTS (mặc định: ja-JP-KeitaNeural)
--skip-video    Bỏ qua bước 7 (chỉ tạo audio + SRT)
--output-dir    Thư mục output (mặc định: ./output)
```

---

## 6. Cách sử dụng với CapCut (Post-production)

Sau khi pipeline chạy xong, user import vào CapCut:

```
1. Mở CapCut → Tạo project mới
2. Import video gốc (input.mp4)
3. Import audio JP (audio_jp_full.wav) → đặt vào audio track 2
4. Import subtitle JP (transcript_jp.srt) → tự động tạo text overlay
5. Mute audio track 1 (audio gốc)
6. Chỉnh sửa thủ công:
   - Kéo giãn/co các đoạn audio JP cho khớp video
   - Sửa subtitle nếu cần
   - Thêm hiệu ứng, nhạc nền
7. Export video final
```

Ngoài ra, thư mục `segments/` chứa từng đoạn audio riêng lẻ (seg_001.wav, seg_002.wav...) nên user có thể import từng đoạn và căn chỉnh chính xác hơn trong CapCut nếu muốn.

---

## 7. Cấu hình môi trường

### .env file

```
# Azure Speech Service
AZURE_SPEECH_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AZURE_SPEECH_REGION=japaneast

# Claude API
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# TTS Settings
TTS_VOICE=ja-JP-KeitaNeural
TTS_SPEED=1.0
```

### System dependencies (cần cài trước)

```bash
# FFmpeg (Windows - dùng winget hoặc choco)
winget install FFmpeg
# hoặc
choco install ffmpeg

# yt-dlp
pip install yt-dlp

# Python packages
pip install azure-cognitiveservices-speech anthropic pydub srt python-dotenv
```

### requirements.txt

```
azure-cognitiveservices-speech>=1.40.0
anthropic>=0.42.0
pydub>=0.25.1
srt>=3.5.3
yt-dlp>=2024.0.0
python-dotenv>=1.0.1
ffmpeg-python>=0.2.0
```

---

## 8. Ước tính chi phí

### Cho 1 video 10 phút

| Service | Mức sử dụng | Chi phí |
|---|---|---|
| Azure ASR (F0 Free) | ~10 phút audio | ¥0 (trong free tier 5h/tháng) |
| Claude API Opus | ~2,000 từ input + output | ~$0.05-0.10 (~¥8-15) |
| Azure TTS (F0 Free) | ~3,000-5,000 ký tự JP | ¥0 (trong free tier 500K chars/tháng) |
| **Tổng** | | **~¥8-15 / video** |

### Nếu vượt Free tier (xử lý nhiều video)

| Service | Pricing (Standard S0) |
|---|---|
| Azure ASR | $1.00 / audio hour |
| Azure TTS Neural | $16.00 / 1M characters |
| Claude API Opus | $15 / 1M input tokens, $75 / 1M output tokens |

### Ước tính chi phí hàng tháng (30 video x 10 phút)

- Azure ASR: 5 giờ → ¥0 (free) hoặc $5.00 (Standard)
- Azure TTS: ~150K ký tự → ¥0 (free) hoặc $2.40 (Standard)
- Claude API: ~60K tokens → ~$1.50
- **Tổng: ~¥0 (free tier) đến ~¥1,400/tháng (Standard)**

---

## 9. Hạn chế và lưu ý

### Hạn chế kỹ thuật
- Tiếng Nhật thường dài hơn tiếng Anh/Việt 20-40% khi đọc → audio JP có thể dài hơn gốc ở một số đoạn. Pipeline sẽ tăng tốc nhẹ (tối đa 40%) nhưng phần còn lại cần user chỉnh trong CapCut.
- ASR có thể không chính xác 100% với audio có nhiều tiếng ồn, giọng nói chồng chéo, hoặc thuật ngữ chuyên ngành.
- Free tier giới hạn 5h ASR và 500K chars TTS mỗi tháng. Nếu cần xử lý nhiều hơn, upgrade lên Standard S0.

### Lưu ý pháp lý
- Đảm bảo có quyền sử dụng video gốc trước khi dubbing.
- yt-dlp download video từ YouTube/TikTok — user chịu trách nhiệm về bản quyền nội dung.
- Azure TTS không được dùng để tạo nội dung lừa đảo hoặc giả mạo danh tính.

### Lưu ý bảo mật
- Không commit API keys vào git. Dùng .env + .gitignore.
- Azure Speech Key có thể regenerate trong Azure Portal nếu bị lộ.

---

## 10. Phát triển tương lai (Optional)

- Hỗ trợ thêm ngôn ngữ đích: Tiếng Hàn, Tiếng Trung, Tiếng Việt
- Tự động lip sync bằng AI (wav2lip, video-retalking)
- Giao diện web đơn giản (Next.js) để paste URL và nhận kết quả
- Batch processing: xử lý nhiều video cùng lúc
- Voice cloning: dùng Azure Custom Neural Voice hoặc ElevenLabs để clone giọng speaker gốc sang tiếng Nhật
- Tích hợp VibeVoice-ASR cho long-form content (>60 phút)
