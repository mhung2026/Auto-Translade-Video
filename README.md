# Auto-Translade-video

Tự động lồng tiếng video (YouTube / TikTok / Douyin / file local) sang **tiếng Việt** hoặc **tiếng Nhật**, giữ nguyên nhạc nền và hiệu ứng âm thanh gốc.

## Pipeline

```
URL/file → Download → Extract audio → (Demucs tách BGM)
        → ASR (Azure Speech) → Dịch sang VI/JP (skill hoặc web AI)
        → TTS (LucyLab cho VI, Azure cho JP)
        → Khớp timeline → Mix với BGM → Ghép vào video
```

## Yêu cầu

- Python 3.10+
- `ffmpeg` trong PATH
- Tài khoản **Azure Speech** (ASR + JP TTS)
- Tài khoản **LucyLab** (chỉ cần nếu lồng VI) – https://lucylab.io
- (Tuỳ chọn) Google Gemini API key (để tự sinh metadata YouTube + thumbnail)

```bash
pip install -r requirements.txt
playwright install chromium      # cần cho download Douyin
cp .env.example .env             # rồi điền key vào
```

## Hai cách dịch — chọn 1

Bước dịch transcript là bước **duy nhất** cần can thiệp tay. Sau khi ASR xong, pipeline tự dừng và tạo file `TRANSLATE_PENDING.txt` trong work dir, chứa hướng dẫn cụ thể cho cả 2 cách dưới.

### Cách A — Người dùng Claude Code (full auto)

Mở repo trong [Claude Code](https://claude.com/claude-code) và bảo:

> Translate the transcript at `output/VN/2026xxxx_vi` to Vietnamese.

Hoặc gọi skill trực tiếp:

```
/translate-video-segments
```

Skill đọc `transcript_original.json`, dịch theo style rules (xem `.claude/skills/translate-video-segments/`), ghi `transcript_vi.json`. Pipeline tự resume.

Toàn bộ workflow từ link đến video xuất ra **chạy 1 lần — không cần can thiệp** vì Claude Code tự chạy `pipeline_vi.py` phase 1, gọi skill, rồi chạy `--resume`.

### Cách B — Không có Claude Code, không cần API key (ChatGPT / Gemini web)

Khi pipeline dừng, mở `<work_dir>/TRANSLATE_PENDING.txt`. File này chứa sẵn một **prompt chuẩn** + hướng dẫn từng bước:

1. Mở `transcript_original.json` trong work dir
2. Mở ChatGPT hoặc Gemini (web). Bắt đầu chat mới
3. Copy đoạn `----- PROMPT TO COPY -----` từ `TRANSLATE_PENDING.txt`, dán vào chat, dán tiếp nội dung `transcript_original.json` rồi gửi
4. AI trả về một JSON array. Copy lại
5. Lưu thành `transcript_vi.json` (UTF-8) cùng folder với `transcript_original.json`
6. Chạy resume:

   ```bash
   python pipeline_vi.py --resume "<work_dir>" --file <video_gốc.mp4>
   ```

Pipeline phát hiện file dịch, skip bước dịch, tiếp tục TTS → mix → xuất video.

> **Lưu ý:** prompt trong `TRANSLATE_PENDING.txt` đã bao gồm rules giọng văn YouTube (bạn/mình/các bạn, drop tiếng đệm 啊/呢/嘛, pinyin tên Trung, romanization tên Hàn), rules length-aware theo duration mỗi segment, và format JSON output strict.

## Sử dụng

### Lồng tiếng Việt

```bash
# YouTube/Douyin URL
python pipeline_vi.py --url "https://v.douyin.com/..." --source-lang zh --voice male

# File local
python pipeline_vi.py --file input/video.mp4 --source-lang zh --voice male

# Tham số BGM
python pipeline_vi.py --url ... --bg-mode demucs          # mặc định, chất lượng
python pipeline_vi.py --url ... --bg-mode duck            # nhanh, giảm -12 dB
python pipeline_vi.py --url ... --bg-mode duck --bg-duck-db -15
python pipeline_vi.py --url ... --bg-mode none            # bỏ BGM
```

### Lồng tiếng Nhật

```bash
python pipeline.py --url ... --source-lang en --voice ja-JP-KeitaNeural
```

### Resume sau khi dịch tay

```bash
python pipeline_vi.py --resume "output/VN/20260601120000_vi" --file input/video.mp4
python pipeline.py --resume "output/20260601120000" --file input/video.mp4
```

### Batch nhiều video

```bash
python batch_run_vi.py --excel output/video_link.xlsx     # VI từ Excel
python batch_run_json.py --json list_video.json          # VI từ JSON
python batch_run.py --excel output/video_link.xlsx       # JP từ Excel
```

## Cấu trúc output

```
output/VN/20260601120000_vi/
├── <video_id>.mp4                  # video gốc đã download
├── original_audio.wav              # audio gốc 16kHz mono
├── no_vocals.wav                   # BGM tách (chỉ khi --bg-mode demucs)
├── vocals.wav                      # giọng tách (chỉ khi --bg-mode demucs)
├── transcript_original.json        # ASR output
├── transcript_original.srt
├── TRANSLATE_PENDING.txt           # hướng dẫn dịch (xoá sau khi dịch xong)
├── transcript_vi.json              # bản dịch (Path A hoặc B tạo)
├── transcript_vi.srt
├── segments/seg_xxx.wav            # TTS từng segment
├── dubbed_audio.wav                # audio cuối (VI + BGM)
└── dubbed_video.mp4                # video cuối
```

## Tính năng

- Download Douyin (Playwright), TikTok, YouTube, 1000+ site qua yt-dlp
- ASR Azure Speech (zh-CN, en, ja, vi, …)
- 3 chế độ BGM:
  - `demucs` — tách giọng/nhạc bằng Demucs (htdemucs), chất lượng cao
  - `duck` — giảm volume audio gốc theo `--bg-duck-db` rồi đè TTS lên
  - `none` — base silent, không giữ BGM
- TTS:
  - **VI** — LucyLab (giọng `male` / `female`)
  - **JP** — Azure Neural Voice (mặc định `ja-JP-KeitaNeural`)
- Timeline fit: tự `atempo` (max 1.4x) khi TTS dài hơn segment gốc
- Resume từ work dir (`--resume`)
- Batch từ Excel hoặc JSON
- Sinh SRT (original + dịch)
- Sinh metadata YouTube (title/description/tags) + thumbnail prompts qua Gemini (nếu có `google_api_key`)

## License

MIT.
