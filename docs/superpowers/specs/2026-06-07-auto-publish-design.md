# Auto-Publish to YouTube + Facebook Page — Design Spec

**Date:** 2026-06-07
**Status:** Design approved, implementation pending
**Author:** Hai (Ho Quang Hai)

## 1. Goal

Sau khi pipeline dub xong và xuất ra `dubbed_video.mp4`, tự động đăng video lên YouTube channel và Facebook Page với metadata được sinh sẵn từ `content_generator.py` (Gemini). Workflow vẫn là một lệnh duy nhất từ link gốc đến video đã đăng.

**Trong scope:** YouTube Data API v3, Facebook Graph API (regular video upload lên Page timeline).
**Ngoài scope (future):** TikTok, Facebook Reels, YouTube Shorts auto-format, custom thumbnail render, analytics, scheduling queue.

## 2. Constraints / Decisions chốt từ brainstorming

| Quyết định | Lý do |
|---|---|
| Entry point: `--upload youtube,facebook` flag tích hợp vào `pipeline_vi.py` / `pipeline.py` | User chốt "auto sau khi dub xong" |
| 1 account/channel/page cố định mỗi platform | Đơn giản; multi-account là YAGNI cho user solo |
| Metadata: reuse `youtube_metadata.json` từ `content_generator.py` cho cả 2 platform | Tiết kiệm Gemini call; đủ tốt cho v1 |
| Default privacy = `private` (YouTube) / `unpublished DRAFT` (FB); có `--public` flag | Tránh đăng nhầm video lỗi |
| Fail-tolerant: 1 platform fail không block platform khác; log error riêng | Re-run command để retry chỉ phần fail |

## 3. Architecture

```
src/publishers/
├── __init__.py           # publish(work_dir, video_path, platforms, public=False) entry
├── base.py               # PublishResult dataclass, PublishError exceptions
├── auth.py               # Token storage/refresh helpers (chung cho 2 platform)
├── youtube.py            # upload() + login CLI command
└── facebook.py           # upload() + setup CLI command
```

Pattern khớp với `src/` hiện tại: mỗi module 1 responsibility. Khi thêm TikTok phase 2 chỉ cần `src/publishers/tiktok.py` + đăng ký trong `__init__.py`, không sửa code cũ.

### Public interface

```python
# src/publishers/__init__.py
from src.publishers.base import PublishResult

PUBLISHERS = {
    'youtube': 'src.publishers.youtube:upload',
    'facebook': 'src.publishers.facebook:upload',
}

def publish(
    work_dir: str,
    video_path: str,
    platforms: list[str],
    public: bool = False,
) -> dict[str, PublishResult]:
    """Run upload on each platform independently. Returns per-platform results."""
```

### PublishResult dataclass

```python
@dataclass
class PublishResult:
    platform: str            # 'youtube' | 'facebook'
    success: bool
    video_id: str | None
    url: str | None
    error: str | None        # short error code: 'quota_exceeded', 'auth_expired', ...
    error_message: str | None  # human-readable
    retryable: bool = False
```

## 4. Pipeline Integration

### CLI flags mới (cả `pipeline_vi.py` và `pipeline.py`)

```python
parser.add_argument(
    "--upload",
    metavar="PLATFORMS",
    help="Comma-separated platforms to publish to after dub: youtube,facebook. "
         "Default: don't upload.",
)
parser.add_argument(
    "--public",
    action="store_true",
    help="Upload as PUBLIC. Default: private/draft (review manually before publishing).",
)
```

### Step 9 — Upload (chạy sau final video merge)

```python
# Trong run_pipeline_vi() / run_pipeline()
if upload_platforms := _parse_upload_arg(args.upload):
    logger.info("=" * 60)
    logger.info(f"STEP 9: Publishing to {','.join(upload_platforms)}")
    from src.publishers import publish
    results = publish(
        work_dir=work_dir,
        video_path=dubbed_video_path,
        platforms=upload_platforms,
        public=args.public,
    )
    _log_publish_summary(results)
    # Pipeline KHÔNG raise nếu upload fail; chỉ log. Video gốc vẫn ở work_dir.
```

### Resume / retry

Khi user chạy `--resume <work_dir> --upload facebook`, pipeline phát hiện `dubbed_video.mp4` đã có → skip toàn bộ Step 1-8 → chỉ chạy Step 9 với platform `facebook`. Cho phép retry upload riêng từng platform.

## 5. YouTube Publisher

### Dependencies thêm vào `requirements.txt`
```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
```

### One-time setup user phải làm
1. Tạo Google Cloud project → enable YouTube Data API v3 → OAuth Client ID type "Desktop app" → download `client_secrets.json`.
2. Copy file vào `~/.auto-translate/youtube_client_secrets.json` (path override qua env `AUTO_TRANSLATE_HOME`).
3. Chạy `python -m src.publishers.youtube login` — pipeline mở browser → user grant scope `https://www.googleapis.com/auth/youtube.upload` → token lưu vào `~/.auto-translate/youtube_token.json` (có `refresh_token`).
4. Lần sau: tự refresh, không cần browser.

### Upload flow

```python
def upload(work_dir: str, video_path: str, public: bool = False) -> PublishResult:
    creds = load_youtube_credentials()                # raises if not logged in
    youtube = build('youtube', 'v3', credentials=creds)
    metadata = _load_metadata(work_dir)               # youtube_metadata.json from content_generator

    body = {
        'snippet': {
            'title': metadata['title'][:100],
            'description': metadata['description'][:5000],
            'tags': metadata.get('hashtags', [])[:30],
            'categoryId': '22',                       # People & Blogs
            'defaultLanguage': 'vi',
        },
        'status': {
            'privacyStatus': 'public' if public else 'private',
            'selfDeclaredMadeForKids': False,
        },
    }
    media = MediaFileUpload(video_path, chunksize=10*1024*1024, resumable=True)
    request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    response = _resumable_upload_with_retry(request)  # backoff on transient errors

    # Optional: thumbnail + caption
    if thumb := _find_thumbnail(work_dir):
        youtube.thumbnails().set(videoId=response['id'], media_body=thumb).execute()
    if srt := _find_vi_srt(work_dir):
        _upload_caption(youtube, response['id'], srt, 'vi')

    return PublishResult(
        platform='youtube', success=True,
        video_id=response['id'],
        url=f"https://youtube.com/watch?v={response['id']}",
    )
```

### Error mapping

| Google API error | PublishResult.error | retryable |
|---|---|---|
| `quotaExceeded` (HTTP 403) | `quota_exceeded` | true |
| `forbidden` (testing-mode user not whitelisted) | `auth_unauthorized` | false |
| `invalidCredentials` (refresh failed) | `auth_expired` | false |
| Transient 5xx | (auto-retry trong upload, không bubble) | — |
| Other | `unknown` | false |

### Quota note
1 upload = ~1,600 units; daily quota mặc định 10,000 units → ~6 upload/ngày/project. README phải hướng dẫn user tạo thêm Google Cloud projects nếu cần volume cao.

## 6. Facebook Page Publisher

### Dependencies
Chỉ dùng `requests` (đã có sẵn). Không cần SDK.

### One-time setup user phải làm
1. Tạo Meta App ở [developers.facebook.com](https://developers.facebook.com/apps) → type "Business" → add Facebook Login product.
2. Lấy `app_id` + `app_secret` từ Settings → Basic. Điền vào `.env`:
   ```
   FACEBOOK_APP_ID=...
   FACEBOOK_APP_SECRET=...
   FACEBOOK_PAGE_ID=...
   ```
3. Mở [Graph API Explorer](https://developers.facebook.com/tools/explorer) → chọn app → Generate User Access Token với permissions:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_manage_engagement`
4. Copy short-lived token → chạy:
   ```bash
   python -m src.publishers.facebook setup --user-token <SHORT_LIVED_TOKEN>
   ```
   Script:
   - Đổi short-lived User Token → long-lived User Token (60 ngày)
   - Lấy long-lived Page Token (vĩnh viễn nếu user không đổi mật khẩu hoặc revoke app)
   - Lưu vào `~/.auto-translate/facebook_token.json`

### App Review note
- **Development mode (default)**: chỉ user roles của App (admin/developer/tester) + admin Page mới dùng được. **Đủ cho cá nhân open source** — README nêu rõ "user phải là admin Page bạn muốn đăng".
- **Live mode** cần submit Meta App Review (1-4 tuần, có thể bị reject). Không bắt buộc cho v1.

### Upload flow (3-phase Graph API video upload)

```python
def upload(work_dir: str, video_path: str, public: bool = False) -> PublishResult:
    cfg = load_facebook_config()                      # page_id + page_token
    metadata = _load_metadata(work_dir)
    description = f"{metadata['title']}\n\n{metadata['description']}"[:8000]
    url = f"https://graph-video.facebook.com/v21.0/{cfg.page_id}/videos"

    # Phase 1: start
    start_resp = requests.post(url, data={
        'upload_phase': 'start',
        'file_size': os.path.getsize(video_path),
        'access_token': cfg.page_token,
    }).json()
    session_id = start_resp['upload_session_id']

    # Phase 2: transfer chunks
    _transfer_chunks(url, session_id, video_path, cfg.page_token, start_resp)

    # Phase 3: finish + publish settings
    finish_data = {
        'upload_phase': 'finish',
        'upload_session_id': session_id,
        'title': metadata['title'][:255],
        'description': description,
        'published': public,
        'access_token': cfg.page_token,
    }
    if not public:
        finish_data['unpublished_content_type'] = 'DRAFT'
    response = requests.post(url, data=finish_data).json()
    video_id = response['video_id']

    return PublishResult(
        platform='facebook', success=True,
        video_id=video_id,
        url=f"https://facebook.com/{video_id}",
    )
```

### Error mapping

| Graph API error code | PublishResult.error | retryable |
|---|---|---|
| 190 (token expired/invalid) | `auth_expired` | false |
| 200 (permission denied) | `auth_permission_denied` | false |
| 4/17/32 (rate limit) | `rate_limited` | true (backoff) |
| 100 (invalid param — file too large) | `validation_failed` | false |
| 5xx | (auto-retry inside `_transfer_chunks`) | — |
| Other | `unknown` | false |

## 7. Auth & Token Storage

### Location

```
$AUTO_TRANSLATE_HOME (default ~/.auto-translate/)
├── youtube_client_secrets.json    # user-provided
├── youtube_token.json             # auto-generated, contains refresh_token
└── facebook_token.json            # auto-generated, contains long-lived page_token
```

`.env` chỉ chứa Facebook App credentials (cần cho `setup` step), không chứa token.

### Security

- `auth.py` chmod 0o600 trên Unix; Windows inherit user-only ACL theo default.
- Logging: bao giờ in token cũng truncate đầu 8 ký tự + `...` (utility `_redact(token)`).
- `.gitignore` thêm `.auto-translate/` failsafe (path nằm ngoài repo nhưng phòng khi user symlink).

### `auth.py` API

```python
def auto_translate_home() -> Path: ...
def load_youtube_credentials() -> Credentials: ...        # raises NotLoggedInError
def save_youtube_credentials(creds: Credentials) -> None: ...
def load_facebook_config() -> FacebookConfig: ...         # page_id + page_token
def save_facebook_token(page_id: str, page_token: str) -> None: ...
def _redact(token: str) -> str: ...                       # for safe logging
```

## 8. Testing Strategy

### Unit tests (mocked, no real API calls)

```
tests/
├── test_publishers_youtube.py
├── test_publishers_facebook.py
├── test_publishers_auth.py
└── fixtures/
    ├── youtube_metadata.json    # sample from content_generator output
    └── fake_video.mp4           # tiny dummy
```

**YouTube** — mock `googleapiclient.discovery.build`:
- happy path returns video_url
- title truncated to 100 chars (boundary)
- quotaExceeded → retryable `quota_exceeded`
- forbidden → non-retryable `auth_unauthorized` with helpful message
- thumbnail uploaded when file exists
- caption uploaded when SRT exists
- `public=False` sets `privacyStatus=private`

**Facebook** — mock `requests.post`:
- 3-phase flow: start → transfer → finish in order
- `public=False` adds `unpublished_content_type=DRAFT`
- token expired error contains "Run setup again"
- rate limit triggers exponential backoff
- file size > 10GB rejected pre-flight

**Auth**:
- token persistence round-trip
- expired access_token triggers refresh via refresh_token
- `_redact()` produces safe log strings

### Integration tests (opt-in, manual)

```
tests/integration/
├── test_youtube_real.py    # @pytest.mark.integration
└── test_facebook_real.py   # @pytest.mark.integration
```

Skipped by default. Run with:
```bash
pytest tests/integration/ --run-integration
```

Upload 5s dummy video private, verify videoId resolves, then cleanup (delete uploaded video). Not run in CI.

### Existing 22 tests unaffected
`src/publishers/*` is greenfield code; touches no existing modules outside adding imports in `pipeline.py` / `pipeline_vi.py`.

## 9. README Updates

Thêm section "Auto-publish" với:
- One-time setup steps per platform (link đến Google Cloud, Meta Developers)
- CLI examples (`--upload youtube`, `--upload youtube,facebook`, `--public`)
- Quota limits and how to handle
- Note about App Review (FB) being optional for personal use
- Troubleshooting common errors

## 10. Out of Scope / Future Work

### Future v2 (sau v1 stable)
- **TikTok** (Approach C trong brainstorming): Content Posting API "Upload to Inbox" path. Pipeline đẩy draft vào TikTok inbox; user mở app bấm Post. Module `src/publishers/tiktok.py` theo cùng pattern.
- **Facebook Reels**: Reels Publishing API riêng (`/{page-id}/video_reels` 3-phase). Cần aspect ratio 9:16 — pipeline cần auto-crop.
- **YouTube Shorts**: Auto detect/convert 16:9 → 9:16 + add `#Shorts` tag.
- **Custom thumbnail render**: Hiện chỉ sinh prompts text; future gọi Gemini image model thật → tạo thumbnail.jpg → upload.
- **Cross-platform metadata variation**: Sinh caption FB riêng (ngắn, emoji-friendly) thay vì dùng title YouTube.

### Explicit non-goals (KHÔNG làm dù v2)
- Analytics scraping (views/likes/comments)
- Multi-account/channel selector per video
- Build scheduling queue riêng (dùng tính năng schedule native của YouTube/FB)
- Comment/reply automation
- Auto-delete video nếu fail upload bước sau

## 11. Open Questions

Không có. Tất cả constraint đã chốt qua brainstorming.

## 12. Implementation Order

Đề xuất build:
1. `src/publishers/base.py` + `auth.py` (interfaces + token storage)
2. `src/publishers/youtube.py` + tests (dễ hơn, ROI cao)
3. Wire vào `pipeline_vi.py` + `pipeline.py` với `--upload` flag
4. End-to-end test với 1 video thật (private upload)
5. `src/publishers/facebook.py` + tests
6. End-to-end test FB private
7. README + docs update
8. Commit + push
