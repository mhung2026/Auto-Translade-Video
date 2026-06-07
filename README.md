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

## Tự động đăng lên YouTube + Facebook Page

Sau khi pipeline dub xong, dùng flag `--upload` để tự đăng video lên các nền tảng đã cấu hình. Mặc định đăng ở chế độ **private/draft** để bạn review trước khi public.

### Setup một lần — YouTube

1. Vào [Google Cloud Console](https://console.cloud.google.com), tạo project → enable **YouTube Data API v3**.
2. APIs & Services → Credentials → Create OAuth Client ID → type "Desktop app" → Download JSON.
3. Lưu file đó vào `~/.auto-translate/youtube_client_secrets.json` (Windows: `C:\Users\<user>\.auto-translate\`).
4. Chạy 1 lần để đăng nhập:
   ```bash
   python -m src.publishers.youtube login
   ```
   Browser sẽ mở → đăng nhập Google → grant scope `youtube.upload`.
5. Kiểm tra:
   ```bash
   python -m src.publishers.youtube whoami
   ```

> **Quota:** mỗi project mặc định 10,000 units/ngày, 1 upload ≈ 1,600 units → ~6 video/ngày. Cần nhiều hơn: tạo thêm Google Cloud projects hoặc apply mở rộng quota.

### Setup một lần — Facebook Page

1. Tạo Meta App tại [developers.facebook.com/apps](https://developers.facebook.com/apps) → type "Business".
2. Lấy **App ID** + **App Secret** ở Settings → Basic. Lấy **Page ID** ở phần "About" của Page.
3. Điền vào `.env`:
   ```
   FACEBOOK_APP_ID=...
   FACEBOOK_APP_SECRET=...
   FACEBOOK_PAGE_ID=...
   ```
4. Vào [Graph API Explorer](https://developers.facebook.com/tools/explorer) → chọn app → Generate User Access Token với scopes:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`.
5. Copy token đó → chạy:
   ```bash
   python -m src.publishers.facebook setup --user-token <PASTED_TOKEN>
   ```
   Script đổi sang long-lived Page Token và lưu vào `~/.auto-translate/facebook_token.json`.
6. Kiểm tra:
   ```bash
   python -m src.publishers.facebook whoami
   ```

> **App Review:** mặc định app ở Development mode → chỉ admin Page bạn sở hữu dùng được, đủ cho cá nhân. Submit App Review chỉ cần thiết nếu cho user ngoài app dùng.

### Sử dụng

```bash
# Đăng lên YouTube (private) sau khi dub xong
python pipeline_vi.py --url "https://v.douyin.com/..." --voice male --upload youtube

# Đăng lên cả 2 platform, vẫn private/draft
python pipeline_vi.py --file video.mp4 --source-lang zh --voice female --upload youtube,facebook

# Đăng public ngay (chỉ khi đã chắc chắn chất lượng)
python pipeline_vi.py --url ... --upload youtube --public

# Retry chỉ riêng Facebook sau khi YouTube đã thành công
python pipeline_vi.py --resume "output/VN/<work_dir>" --file <video> --upload facebook
```

### Hành vi khi fail

Mỗi platform fail độc lập — pipeline KHÔNG raise. Cuối log in summary:

```
STEP 9: Publishing to youtube, facebook (privacy=private/draft)
  [OK] youtube: https://youtube.com/watch?v=abc
  [FAIL] facebook: auth_expired — Facebook page token is no longer valid. Run setup again: ...
```

Re-run với `--resume <work_dir> --upload facebook` để retry riêng platform fail.

## License

MIT.
