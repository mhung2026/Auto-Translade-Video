# Auto-Publish to YouTube + Facebook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--upload youtube,facebook` flag to the dub pipelines so a finished `dubbed_video.mp4` auto-publishes to a configured YouTube channel and Facebook Page, defaulting to private/draft for safety, with per-platform success/failure isolation.

**Architecture:** Per-platform modules under `src/publishers/` exposing a single `upload(work_dir, video_path, public) -> PublishResult` function. Shared `auth.py` for token storage in `~/.auto-translate/`. Pipeline calls `publishers.publish(...)` after the final video merge step and logs a summary; pipeline never fails because of upload errors.

**Tech Stack:** `google-api-python-client` + `google-auth-oauthlib` for YouTube, plain `requests` for Facebook Graph API v21.0, pytest for tests.

**Reference spec:** `docs/superpowers/specs/2026-06-07-auto-publish-design.md`

---

## File Structure

**Create:**
- `src/publishers/__init__.py` — `publish()` entry point + registry
- `src/publishers/base.py` — `PublishResult` dataclass, error codes, `_redact()`
- `src/publishers/auth.py` — token storage helpers (`auto_translate_home`, save/load credentials)
- `src/publishers/youtube.py` — `upload()` + `login` / `whoami` CLI subcommands
- `src/publishers/facebook.py` — `upload()` + `setup` / `whoami` CLI subcommands
- `tests/test_publishers_base.py` — base + auth tests
- `tests/test_publishers_youtube.py` — YouTube upload tests (mocked)
- `tests/test_publishers_facebook.py` — Facebook upload tests (mocked)
- `tests/fixtures/youtube_metadata.json` — sample metadata fixture

**Modify:**
- `pipeline_vi.py` — add `--upload`, `--public` flags + STEP 9 publish call
- `pipeline.py` — same as `pipeline_vi.py`
- `requirements.txt` — add YouTube API libs
- `.env.example` — add Facebook App credentials
- `.gitignore` — add `.auto-translate/` failsafe
- `README.md` — add Auto-Publish section

---

## Task 1: Foundation — base.py, auth helpers, dependencies

**Files:**
- Create: `src/publishers/__init__.py`
- Create: `src/publishers/base.py`
- Create: `src/publishers/auth.py`
- Create: `tests/test_publishers_base.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Add deps to requirements.txt**

Append after the existing `soundfile>=0.13.0` line:

```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
```

- [ ] **Step 2: Install deps**

Run: `pip install -r requirements.txt`
Expected: 3 new packages installed, no version conflicts.

- [ ] **Step 3: Add `.auto-translate/` to .gitignore**

Append under the "AI / dev-tool local state" section:

```
.auto-translate/
```

- [ ] **Step 4: Write the failing test for base.py**

Create `tests/test_publishers_base.py`:

```python
"""Tests for src.publishers.base — PublishResult dataclass + utilities."""
import pytest


def test_publish_result_success_minimal():
    from src.publishers.base import PublishResult
    r = PublishResult(platform="youtube", success=True, video_id="abc", url="https://youtube.com/watch?v=abc")
    assert r.platform == "youtube"
    assert r.success is True
    assert r.video_id == "abc"
    assert r.error is None
    assert r.retryable is False


def test_publish_result_failure():
    from src.publishers.base import PublishResult
    r = PublishResult(
        platform="facebook", success=False,
        video_id=None, url=None,
        error="auth_expired", error_message="Token expired. Run setup again.",
        retryable=False,
    )
    assert r.success is False
    assert r.error == "auth_expired"


def test_redact_short_token_does_not_crash():
    from src.publishers.base import redact
    assert redact("abc") == "abc..."   # short tokens still get suffix
    assert redact("") == "..."


def test_redact_long_token_shows_first_8_chars_only():
    from src.publishers.base import redact
    out = redact("ya29.A0AfH6SMBxxxxxxxxxxxxxxxxxxxxxx")
    assert out.startswith("ya29.A0A")
    assert "xxxxxxxx" not in out
    assert out.endswith("...")
```

- [ ] **Step 5: Run base tests, expect failure**

Run: `pytest tests/test_publishers_base.py -v`
Expected: ImportError / ModuleNotFoundError for `src.publishers.base`.

- [ ] **Step 6: Implement base.py**

Create `src/publishers/__init__.py` (empty for now, populated in Task 5):

```python
"""Publishers — upload dubbed videos to YouTube / Facebook / (future) TikTok."""
```

Create `src/publishers/base.py`:

```python
"""Shared types and utilities for publishers."""
from dataclasses import dataclass


@dataclass
class PublishResult:
    """Outcome of a single platform upload attempt."""
    platform: str
    success: bool
    video_id: str | None = None
    url: str | None = None
    error: str | None = None
    error_message: str | None = None
    retryable: bool = False


def redact(token: str) -> str:
    """Return a safe-to-log version of a token: first 8 chars + ellipsis."""
    return token[:8] + "..."
```

- [ ] **Step 7: Run base tests, expect pass**

Run: `pytest tests/test_publishers_base.py -v`
Expected: 4 passed.

- [ ] **Step 8: Write the failing test for auth.py home directory**

Append to `tests/test_publishers_base.py`:

```python
def test_auto_translate_home_uses_env_override(tmp_path, monkeypatch):
    from src.publishers import auth
    monkeypatch.setenv("AUTO_TRANSLATE_HOME", str(tmp_path / "custom"))
    home = auth.auto_translate_home()
    assert home == tmp_path / "custom"
    assert home.exists()                                  # auto-created


def test_auto_translate_home_default_when_no_env(monkeypatch, tmp_path):
    from src.publishers import auth
    monkeypatch.delenv("AUTO_TRANSLATE_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    home = auth.auto_translate_home()
    assert home == tmp_path / ".auto-translate"
    assert home.exists()
```

- [ ] **Step 9: Run, expect failure**

Run: `pytest tests/test_publishers_base.py::test_auto_translate_home_uses_env_override -v`
Expected: ImportError on `auth`.

- [ ] **Step 10: Implement auth.py home helper**

Create `src/publishers/auth.py`:

```python
"""Token storage / refresh helpers shared between publisher modules.

Storage location:
  ~/.auto-translate/
  ├── youtube_client_secrets.json   (user-provided)
  ├── youtube_token.json            (auto-generated after login)
  └── facebook_token.json           (auto-generated after setup)

Override the parent directory via env var AUTO_TRANSLATE_HOME.
"""
import os
from pathlib import Path


def auto_translate_home() -> Path:
    """Return the directory holding publisher credentials. Create if missing."""
    override = os.environ.get("AUTO_TRANSLATE_HOME")
    home = Path(override) if override else Path.home() / ".auto-translate"
    home.mkdir(parents=True, exist_ok=True)
    return home
```

- [ ] **Step 11: Run, expect pass**

Run: `pytest tests/test_publishers_base.py -v`
Expected: 6 passed.

- [ ] **Step 12: Commit**

```bash
git add requirements.txt .gitignore src/publishers/__init__.py src/publishers/base.py src/publishers/auth.py tests/test_publishers_base.py
git commit -m "feat: scaffold publishers package — base types + auth home helper"
```

---

## Task 2: YouTube credentials — load/save + login CLI

**Files:**
- Modify: `src/publishers/auth.py`
- Create: `src/publishers/youtube.py` (login command only this task)
- Modify: `tests/test_publishers_base.py` (add auth tests)

- [ ] **Step 1: Write failing test for YouTube credentials load**

Append to `tests/test_publishers_base.py`:

```python
def test_load_youtube_credentials_raises_when_missing(tmp_path, monkeypatch):
    from src.publishers import auth
    monkeypatch.setenv("AUTO_TRANSLATE_HOME", str(tmp_path))
    with pytest.raises(auth.NotLoggedInError) as exc:
        auth.load_youtube_credentials()
    assert "youtube_token.json" in str(exc.value)


def test_save_then_load_youtube_credentials_roundtrip(tmp_path, monkeypatch):
    from src.publishers import auth
    monkeypatch.setenv("AUTO_TRANSLATE_HOME", str(tmp_path))

    fake_creds_payload = {
        "token": "ya29.fake",
        "refresh_token": "1//fake_refresh",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake.apps.googleusercontent.com",
        "client_secret": "fake_secret",
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    }
    auth.save_youtube_credentials_dict(fake_creds_payload)

    loaded = auth.load_youtube_credentials_dict()
    assert loaded["refresh_token"] == "1//fake_refresh"
    assert loaded["client_id"] == "fake.apps.googleusercontent.com"
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_publishers_base.py::test_load_youtube_credentials_raises_when_missing -v`
Expected: AttributeError on `auth.NotLoggedInError`.

- [ ] **Step 3: Add YouTube credential helpers to auth.py**

Append to `src/publishers/auth.py`:

```python
import json


class NotLoggedInError(Exception):
    """Raised when a publisher requires login but no token exists."""


YOUTUBE_TOKEN_FILE = "youtube_token.json"
YOUTUBE_CLIENT_SECRETS_FILE = "youtube_client_secrets.json"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def youtube_token_path() -> Path:
    return auto_translate_home() / YOUTUBE_TOKEN_FILE


def youtube_client_secrets_path() -> Path:
    return auto_translate_home() / YOUTUBE_CLIENT_SECRETS_FILE


def save_youtube_credentials_dict(payload: dict) -> None:
    """Write the credentials JSON. Caller is responsible for shape."""
    path = youtube_token_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_youtube_credentials_dict() -> dict:
    """Return the raw credentials JSON. Raises NotLoggedInError if absent."""
    path = youtube_token_path()
    if not path.exists():
        raise NotLoggedInError(
            f"Not logged in to YouTube. Expected token at {path}. "
            f"Run: python -m src.publishers.youtube login"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_youtube_credentials():
    """Return a refreshed google.oauth2.credentials.Credentials object."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    data = load_youtube_credentials_dict()
    creds = Credentials.from_authorized_user_info(data, YOUTUBE_SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_youtube_credentials_dict(json.loads(creds.to_json()))
        else:
            raise NotLoggedInError(
                "Stored YouTube token is invalid and cannot be refreshed. "
                "Run: python -m src.publishers.youtube login"
            )
    return creds
```

- [ ] **Step 4: Run tests, expect pass**

Run: `pytest tests/test_publishers_base.py -v`
Expected: 8 passed.

- [ ] **Step 5: Write the YouTube login CLI**

Create `src/publishers/youtube.py`:

```python
"""YouTube publisher — upload video + login CLI.

CLI:
    python -m src.publishers.youtube login    # one-time OAuth flow
    python -m src.publishers.youtube whoami   # show authorized channel
"""
import argparse
import json
import sys

from src.publishers import auth


def login() -> None:
    """Run the OAuth installed-app flow and store the resulting token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets_path = auth.youtube_client_secrets_path()
    if not secrets_path.exists():
        print(
            f"ERROR: {secrets_path} not found.\n"
            f"Steps to fix:\n"
            f"  1. Go to https://console.cloud.google.com\n"
            f"  2. Create a project + enable 'YouTube Data API v3'\n"
            f"  3. APIs & Services > Credentials > Create OAuth Client ID\n"
            f"     type='Desktop app' > Download JSON\n"
            f"  4. Save the downloaded file as: {secrets_path}\n"
            f"  5. Re-run this command.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), auth.YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    auth.save_youtube_credentials_dict(json.loads(creds.to_json()))
    print(f"Logged in. Token saved to {auth.youtube_token_path()}")


def whoami() -> None:
    """Print the authorized YouTube channel name."""
    from googleapiclient.discovery import build

    creds = auth.load_youtube_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        print("No channel found for this account.")
        return
    snippet = items[0]["snippet"]
    print(f"Channel: {snippet['title']}  (id={items[0]['id']})")


def main():
    parser = argparse.ArgumentParser(prog="python -m src.publishers.youtube")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Run one-time OAuth flow")
    sub.add_parser("whoami", help="Show authorized YouTube channel")
    args = parser.parse_args()

    if args.cmd == "login":
        login()
    elif args.cmd == "whoami":
        whoami()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke test the CLI (no real OAuth yet)**

Run: `python -m src.publishers.youtube login`
Expected: Helpful error message about missing `youtube_client_secrets.json` (since user hasn't set it up).

- [ ] **Step 7: Commit**

```bash
git add src/publishers/auth.py src/publishers/youtube.py tests/test_publishers_base.py
git commit -m "feat: YouTube credentials store + login CLI"
```

---

## Task 3: YouTube upload — metadata mapping, resumable upload, error mapping

**Files:**
- Modify: `src/publishers/youtube.py` (add `upload()`)
- Create: `tests/fixtures/youtube_metadata.json`
- Create: `tests/test_publishers_youtube.py`

- [ ] **Step 1: Create metadata fixture**

Create `tests/fixtures/youtube_metadata.json`:

```json
{
  "title": "Bể cá đáy 676 — hướng dẫn hệ tuần hoàn nước",
  "description": "Video hướng dẫn nguyên lý tuần hoàn nước cho bể cá đáy 676. Cách thiết kế cửa F, khu tràn đôi, lọc khô ướt và lọc sinh hóa chữ S. Phù hợp cho người mới chơi cá cảnh.",
  "hashtags": ["#bể_cá", "#lọc_nước", "#aquarium", "#diy"]
}
```

- [ ] **Step 2: Write the failing test — happy path with mocked API**

Create `tests/test_publishers_youtube.py`:

```python
"""Tests for YouTube upload module — all API calls mocked."""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def work_dir(tmp_path):
    """A minimal work_dir with metadata + fake video file."""
    (tmp_path / "youtube_metadata.json").write_text(
        (FIXTURES / "youtube_metadata.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "dubbed_video.mp4").write_bytes(b"fake_mp4_bytes")
    return tmp_path


def _mock_youtube_service(video_id="VID_abc123"):
    """Build a mock youtube service whose insert().execute() returns video_id."""
    service = MagicMock()
    insert_request = MagicMock()
    insert_request.next_chunk.side_effect = [
        (None, None),                                       # progress, no response
        (None, {"id": video_id}),                           # final chunk, got response
    ]
    service.videos.return_value.insert.return_value = insert_request
    service.thumbnails.return_value.set.return_value.execute.return_value = {}
    service.captions.return_value.insert.return_value.execute.return_value = {"id": "CAP_x"}
    return service


def test_upload_happy_path_returns_video_url(work_dir):
    from src.publishers import youtube as yt

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        mock_build.return_value = _mock_youtube_service(video_id="VID_abc123")

        result = yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is True
    assert result.platform == "youtube"
    assert result.video_id == "VID_abc123"
    assert result.url == "https://youtube.com/watch?v=VID_abc123"


def test_upload_truncates_title_to_100_chars(work_dir):
    from src.publishers import youtube as yt

    long_title = "A" * 200
    meta_path = work_dir / "youtube_metadata.json"
    meta_path.write_text(json.dumps({"title": long_title, "description": "", "hashtags": []}), encoding="utf-8")

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = _mock_youtube_service()
        mock_build.return_value = service
        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

        # Inspect the body passed to insert()
        call_kwargs = service.videos.return_value.insert.call_args.kwargs
        assert len(call_kwargs["body"]["snippet"]["title"]) == 100


def test_upload_public_flag_sets_privacy_status(work_dir):
    from src.publishers import youtube as yt

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = _mock_youtube_service()
        mock_build.return_value = service

        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=True)
        body = service.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "public"

        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)
        body = service.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "private"


def test_upload_caps_tags_at_30(work_dir):
    from src.publishers import youtube as yt

    many_tags = [f"#tag{i}" for i in range(60)]
    meta_path = work_dir / "youtube_metadata.json"
    meta_path.write_text(json.dumps({"title": "t", "description": "d", "hashtags": many_tags}), encoding="utf-8")

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = _mock_youtube_service()
        mock_build.return_value = service
        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

        body = service.videos.return_value.insert.call_args.kwargs["body"]
        assert len(body["snippet"]["tags"]) == 30


def test_upload_quota_exceeded_returns_retryable_error(work_dir):
    from googleapiclient.errors import HttpError
    from src.publishers import youtube as yt

    quota_error = HttpError(
        resp=MagicMock(status=403, reason="quotaExceeded"),
        content=b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}',
    )

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = MagicMock()
        service.videos.return_value.insert.return_value.next_chunk.side_effect = quota_error
        mock_build.return_value = service

        result = yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is False
    assert result.error == "quota_exceeded"
    assert result.retryable is True


def test_upload_not_logged_in_returns_failure(work_dir):
    from src.publishers import youtube as yt
    from src.publishers.auth import NotLoggedInError

    with patch.object(yt.auth, "load_youtube_credentials", side_effect=NotLoggedInError("no token")):
        result = yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is False
    assert result.error == "auth_not_logged_in"
    assert result.retryable is False
```

- [ ] **Step 3: Run tests, expect failures**

Run: `pytest tests/test_publishers_youtube.py -v`
Expected: All 6 tests fail because `upload()` does not exist yet.

- [ ] **Step 4: Implement upload() in youtube.py**

Append to `src/publishers/youtube.py` (after the `whoami()` function, before `main()`):

```python
import json
import os

from src.publishers.base import PublishResult


def _build_service(creds):
    """Indirection point so tests can mock the service builder."""
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds)


def _load_metadata(work_dir: str) -> dict:
    path = os.path.join(work_dir, "youtube_metadata.json")
    if not os.path.exists(path):
        # Fall back to a minimal usable metadata so the pipeline doesn't crash.
        return {"title": "Video", "description": "", "hashtags": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _find_thumbnail(work_dir: str) -> str | None:
    for name in ("thumbnail.jpg", "thumbnail.png", "thumbnail_original.jpg"):
        candidate = os.path.join(work_dir, name)
        if os.path.exists(candidate):
            return candidate
    return None


def _find_vi_srt(work_dir: str) -> str | None:
    candidate = os.path.join(work_dir, "transcript_vi.srt")
    return candidate if os.path.exists(candidate) else None


def _map_http_error(http_err) -> tuple[str, str, bool]:
    """Map googleapiclient HttpError to (code, message, retryable)."""
    reason = ""
    try:
        body = json.loads(http_err.content.decode("utf-8"))
        reason = body.get("error", {}).get("errors", [{}])[0].get("reason", "")
    except Exception:
        reason = ""

    if reason == "quotaExceeded":
        return "quota_exceeded", "YouTube daily quota exceeded. Try again tomorrow or use a different project.", True
    if reason in ("forbidden", "youtubeSignupRequired"):
        return "auth_unauthorized", f"YouTube refused upload ({reason}). Check OAuth scopes / test-user whitelist.", False
    if reason == "invalidCredentials":
        return "auth_expired", "Stored YouTube token is no longer valid. Run 'python -m src.publishers.youtube login' again.", False
    return "unknown", f"YouTube API error: {reason or 'no reason'}", False


def upload(work_dir: str, video_path: str, public: bool = False) -> PublishResult:
    """Upload dubbed video to YouTube. Never raises — returns PublishResult."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    try:
        creds = auth.load_youtube_credentials()
    except auth.NotLoggedInError as e:
        return PublishResult(
            platform="youtube", success=False,
            error="auth_not_logged_in", error_message=str(e), retryable=False,
        )

    youtube = _build_service(creds)
    metadata = _load_metadata(work_dir)

    body = {
        "snippet": {
            "title": metadata.get("title", "Video")[:100],
            "description": metadata.get("description", "")[:5000],
            "tags": metadata.get("hashtags", [])[:30],
            "categoryId": "22",                                # People & Blogs
            "defaultLanguage": "vi",
        },
        "status": {
            "privacyStatus": "public" if public else "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=10 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    try:
        response = None
        while response is None:
            _, response = request.next_chunk()
    except HttpError as e:
        code, msg, retryable = _map_http_error(e)
        return PublishResult(
            platform="youtube", success=False,
            error=code, error_message=msg, retryable=retryable,
        )

    video_id = response["id"]
    url = f"https://youtube.com/watch?v={video_id}"

    # Best-effort thumbnail + caption upload — failures here don't fail the publish.
    if thumb := _find_thumbnail(work_dir):
        try:
            youtube.thumbnails().set(videoId=video_id, media_body=thumb).execute()
        except HttpError:
            pass
    if srt := _find_vi_srt(work_dir):
        try:
            _upload_caption(youtube, video_id, srt, "vi")
        except HttpError:
            pass

    return PublishResult(
        platform="youtube", success=True,
        video_id=video_id, url=url,
    )


def _upload_caption(youtube, video_id: str, srt_path: str, lang: str) -> None:
    from googleapiclient.http import MediaFileUpload
    youtube.captions().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id, "language": lang, "name": lang, "isDraft": False}},
        media_body=MediaFileUpload(srt_path, mimetype="application/octet-stream"),
    ).execute()
```

- [ ] **Step 5: Run tests, expect pass**

Run: `pytest tests/test_publishers_youtube.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run full test suite to catch regressions**

Run: `pytest -q`
Expected: All tests pass (22 existing + new ones = 28+).

- [ ] **Step 7: Commit**

```bash
git add src/publishers/youtube.py tests/test_publishers_youtube.py tests/fixtures/youtube_metadata.json
git commit -m "feat: YouTube resumable upload with metadata + thumbnail + caption"
```

---

## Task 4: Publishers entry point — `publish()` dispatcher

**Files:**
- Modify: `src/publishers/__init__.py`
- Modify: `tests/test_publishers_base.py` (add dispatcher tests)

- [ ] **Step 1: Write the failing test for publish()**

Append to `tests/test_publishers_base.py`:

```python
def test_publish_unknown_platform_returns_failure(tmp_path):
    from src.publishers import publish
    results = publish(
        work_dir=str(tmp_path),
        video_path=str(tmp_path / "video.mp4"),
        platforms=["myspace"],
    )
    assert "myspace" in results
    assert results["myspace"].success is False
    assert results["myspace"].error == "unknown_platform"


def test_publish_runs_each_platform_independently(tmp_path, monkeypatch):
    from src.publishers import base, publish

    call_log = []

    def fake_yt(work_dir, video_path, public=False):
        call_log.append(("youtube", work_dir, public))
        return base.PublishResult(platform="youtube", success=True, video_id="A", url="u")

    def fake_fb(work_dir, video_path, public=False):
        call_log.append(("facebook", work_dir, public))
        raise RuntimeError("boom")

    monkeypatch.setattr("src.publishers.youtube.upload", fake_yt)
    monkeypatch.setattr("src.publishers.facebook.upload", fake_fb, raising=False)

    results = publish(
        work_dir=str(tmp_path),
        video_path=str(tmp_path / "v.mp4"),
        platforms=["youtube", "facebook"],
        public=True,
    )

    assert results["youtube"].success is True
    assert results["facebook"].success is False
    assert results["facebook"].error == "exception"
    assert "boom" in results["facebook"].error_message
    assert [c[0] for c in call_log] == ["youtube", "facebook"]
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_publishers_base.py::test_publish_unknown_platform_returns_failure -v`
Expected: ImportError on `publish`.

- [ ] **Step 3: Implement publish() in __init__.py**

Replace `src/publishers/__init__.py` content with:

```python
"""Publishers — upload dubbed videos to YouTube / Facebook / (future) TikTok.

Public entry point:

    from src.publishers import publish
    results = publish(work_dir, video_path, platforms=["youtube", "facebook"], public=False)
"""
import importlib
import logging

from src.publishers.base import PublishResult

logger = logging.getLogger(__name__)

REGISTRY = {
    "youtube": "src.publishers.youtube",
    "facebook": "src.publishers.facebook",
}


def publish(
    work_dir: str,
    video_path: str,
    platforms: list[str],
    public: bool = False,
) -> dict[str, PublishResult]:
    """Run `upload(work_dir, video_path, public)` on each platform sequentially.

    One platform failing does NOT block the others. Each platform's exception
    is caught and reflected as a failure PublishResult.
    """
    results: dict[str, PublishResult] = {}
    for platform in platforms:
        module_name = REGISTRY.get(platform)
        if module_name is None:
            results[platform] = PublishResult(
                platform=platform, success=False,
                error="unknown_platform",
                error_message=f"Unknown publisher: {platform}. Known: {sorted(REGISTRY)}",
            )
            continue
        try:
            module = importlib.import_module(module_name)
            results[platform] = module.upload(work_dir, video_path, public=public)
        except Exception as e:
            logger.exception(f"Publisher '{platform}' raised an exception")
            results[platform] = PublishResult(
                platform=platform, success=False,
                error="exception",
                error_message=f"{type(e).__name__}: {e}",
                retryable=False,
            )
    return results
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_publishers_base.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/publishers/__init__.py tests/test_publishers_base.py
git commit -m "feat: publish() dispatcher — per-platform isolation"
```

---

## Task 5: Wire `--upload` flag into pipeline_vi.py and pipeline.py

**Files:**
- Modify: `pipeline_vi.py`
- Modify: `pipeline.py`

- [ ] **Step 1: Add `--upload` and `--public` args to pipeline_vi.py**

In `pipeline_vi.py`, locate the argparse block (search for the existing `--bg-duck-db` argument) and append:

```python
    parser.add_argument(
        "--upload",
        metavar="PLATFORMS",
        default="",
        help="Comma-separated platforms to publish to after dub (e.g. 'youtube,facebook'). "
             "Default: don't upload.",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Upload as PUBLIC. Default: private/draft (review manually before publishing).",
    )
```

- [ ] **Step 2: Add upload args to `main()` and `run_pipeline_vi()` call site**

In `pipeline_vi.py` `main()`, locate the `run_pipeline_vi(...)` call and append two new kwargs:

```python
            bg_duck_db=args.bg_duck_db,
            upload_platforms=[p.strip() for p in args.upload.split(",") if p.strip()],
            public=args.public,
```

Modify the `run_pipeline_vi()` signature to accept them:

```python
def run_pipeline_vi(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice_id: str,
    skip_video: bool,
    output_dir: str,
    resume_dir: str | None = None,
    bg_mode: str = "demucs",
    bg_duck_db: float = -12.0,
    upload_platforms: list[str] | None = None,
    public: bool = False,
) -> dict:
```

- [ ] **Step 3: Add STEP 9 upload block to pipeline_vi.py**

In `pipeline_vi.py` `run_pipeline_vi()`, locate the `# --- Generate report ---` line (around line 445). The block must go BETWEEN the existing STEP 8 metadata block and the `# --- Generate report ---` line, so it has access to `dubbed_video_path` and `youtube_metadata.json`. Insert:

```python
    # --- Step 9: Publish to YouTube / Facebook ---
    if upload_platforms and dubbed_video_path:
        logger.info("=" * 60)
        logger.info(f"STEP 9: Publishing to {', '.join(upload_platforms)} "
                    f"(privacy={'public' if public else 'private/draft'})")
        from src.publishers import publish
        publish_results = publish(
            work_dir=work_dir,
            video_path=dubbed_video_path,
            platforms=upload_platforms,
            public=public,
        )
        for platform_name, res in publish_results.items():
            if res.success:
                logger.info(f"  [OK] {platform_name}: {res.url}")
            else:
                logger.error(f"  [FAIL] {platform_name}: {res.error} - {res.error_message}")
    elif upload_platforms and not dubbed_video_path:
        logger.warning("STEP 9 skipped: --upload requested but --skip-video produced no video file")
```

(The `if upload_platforms and dubbed_video_path` guard handles `--skip-video` and `--upload` being passed together — pipeline logs a warning instead of crashing.)

- [ ] **Step 4: Add CLI args + STEP 9 to pipeline.py**

In `pipeline.py`, locate the argparse block in `parse_args()` (search for the existing `--bg-duck-db` argument) and append the same two argument blocks added to `pipeline_vi.py` in Step 1:

```python
    parser.add_argument(
        "--upload",
        metavar="PLATFORMS",
        default="",
        help="Comma-separated platforms to publish to after dub (e.g. 'youtube,facebook'). "
             "Default: don't upload.",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Upload as PUBLIC. Default: private/draft (review manually before publishing).",
    )
```

Modify `pipeline.py` `run_pipeline()` signature to add two kwargs (keep `voice` not `voice_id`):

```python
def run_pipeline(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice: str,
    skip_video: bool,
    output_dir: str,
    resume_dir: str | None = None,
    bg_mode: str = "demucs",
    bg_duck_db: float = -12.0,
    upload_platforms: list[str] | None = None,
    public: bool = False,
) -> dict:
```

In `pipeline.py` `main()`, locate the `run_pipeline(...)` call and append the same two kwargs:

```python
            bg_duck_db=args.bg_duck_db,
            upload_platforms=[p.strip() for p in args.upload.split(",") if p.strip()],
            public=args.public,
```

Finally, in `pipeline.py` `run_pipeline()`, locate the `# --- Generate report ---` line and insert:

```python
    # --- Step 9: Publish to YouTube / Facebook ---
    if upload_platforms and dubbed_video_path:
        logger.info("=" * 60)
        logger.info(f"STEP 9: Publishing to {', '.join(upload_platforms)} "
                    f"(privacy={'public' if public else 'private/draft'})")
        from src.publishers import publish
        publish_results = publish(
            work_dir=work_dir,
            video_path=dubbed_video_path,
            platforms=upload_platforms,
            public=public,
        )
        for platform_name, res in publish_results.items():
            if res.success:
                logger.info(f"  [OK] {platform_name}: {res.url}")
            else:
                logger.error(f"  [FAIL] {platform_name}: {res.error} - {res.error_message}")
    elif upload_platforms and not dubbed_video_path:
        logger.warning("STEP 9 skipped: --upload requested but --skip-video produced no video file")
```

- [ ] **Step 5: Verify both CLIs parse the new args**

Run (Windows PowerShell with UTF-8): `$env:PYTHONIOENCODING="utf-8"; python pipeline_vi.py --help | Select-String "upload|public"`
Expected: 2 lines mentioning `--upload` and `--public`.

Run: `$env:PYTHONIOENCODING="utf-8"; python pipeline.py --help | Select-String "upload|public"`
Expected: 2 lines mentioning `--upload` and `--public`.

- [ ] **Step 6: Re-run full test suite**

Run: `pytest -q`
Expected: All tests still pass (no test for the new pipeline branch yet — that branch is manual/integration territory).

- [ ] **Step 7: Commit**

```bash
git add pipeline_vi.py pipeline.py
git commit -m "feat: wire --upload / --public flags into pipelines"
```

---

## Task 6: Facebook credentials — config storage + setup CLI

**Files:**
- Modify: `src/publishers/auth.py`
- Create: `src/publishers/facebook.py` (setup command only this task)
- Modify: `tests/test_publishers_base.py` (add FB config tests)
- Modify: `.env.example`

- [ ] **Step 1: Append FB env keys to .env.example**

Append to `.env.example`:

```
# Facebook upload (only needed if you use --upload facebook)
# 1) Create a Meta App at https://developers.facebook.com/apps (type: Business)
# 2) Get App ID + App Secret from Settings > Basic
# 3) Page ID is shown in your Facebook Page's "About" section
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_PAGE_ID=
```

- [ ] **Step 2: Write the failing test for FB config**

Append to `tests/test_publishers_base.py`:

```python
def test_facebook_config_load_raises_when_missing(tmp_path, monkeypatch):
    from src.publishers import auth
    monkeypatch.setenv("AUTO_TRANSLATE_HOME", str(tmp_path))
    with pytest.raises(auth.NotLoggedInError):
        auth.load_facebook_config()


def test_save_then_load_facebook_token_roundtrip(tmp_path, monkeypatch):
    from src.publishers import auth
    monkeypatch.setenv("AUTO_TRANSLATE_HOME", str(tmp_path))
    auth.save_facebook_token(page_id="1234567890", page_token="EAAB_fake_page_token")
    cfg = auth.load_facebook_config()
    assert cfg.page_id == "1234567890"
    assert cfg.page_token == "EAAB_fake_page_token"
```

- [ ] **Step 3: Run, expect failure**

Run: `pytest tests/test_publishers_base.py -k facebook -v`
Expected: AttributeError on `auth.load_facebook_config`.

- [ ] **Step 4: Add Facebook helpers to auth.py**

Append to `src/publishers/auth.py`:

```python
from dataclasses import dataclass


FACEBOOK_TOKEN_FILE = "facebook_token.json"


@dataclass
class FacebookConfig:
    page_id: str
    page_token: str


def facebook_token_path() -> Path:
    return auto_translate_home() / FACEBOOK_TOKEN_FILE


def save_facebook_token(page_id: str, page_token: str) -> None:
    path = facebook_token_path()
    path.write_text(
        json.dumps({"page_id": page_id, "page_token": page_token}, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_facebook_config() -> FacebookConfig:
    path = facebook_token_path()
    if not path.exists():
        raise NotLoggedInError(
            f"Facebook not configured. Expected token at {path}. "
            f"Run: python -m src.publishers.facebook setup --user-token <SHORT_LIVED_TOKEN>"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return FacebookConfig(page_id=data["page_id"], page_token=data["page_token"])
```

- [ ] **Step 5: Run, expect pass**

Run: `pytest tests/test_publishers_base.py -k facebook -v`
Expected: 2 passed.

- [ ] **Step 6: Create facebook.py with setup + whoami CLI**

Create `src/publishers/facebook.py`:

```python
"""Facebook Page publisher — upload video + setup CLI.

CLI:
    python -m src.publishers.facebook setup --user-token <SHORT_LIVED>
        # exchanges for long-lived page token, stores it
    python -m src.publishers.facebook whoami
        # prints the configured Page name + id
"""
import argparse
import os
import sys

import requests
from dotenv import load_dotenv

from src.publishers import auth

load_dotenv()                                # populate FACEBOOK_APP_ID etc. without forcing config.py


GRAPH_API = "https://graph.facebook.com/v21.0"


def _env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        print(
            f"ERROR: {key} not set. Add it to .env (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def setup(user_token: str) -> None:
    """Exchange a short-lived user token for a long-lived Page Access Token and store it."""
    app_id = _env("FACEBOOK_APP_ID")
    app_secret = _env("FACEBOOK_APP_SECRET")
    page_id = _env("FACEBOOK_PAGE_ID")

    # Step 1: short-lived user token → long-lived user token (60 days)
    r = requests.get(
        f"{GRAPH_API}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": user_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    long_user_token = r.json()["access_token"]
    print("Long-lived user token acquired.")

    # Step 2: long-lived user token → page accounts → page-specific token
    r = requests.get(
        f"{GRAPH_API}/me/accounts",
        params={"access_token": long_user_token},
        timeout=30,
    )
    r.raise_for_status()
    page_token = None
    for page in r.json().get("data", []):
        if page["id"] == page_id:
            page_token = page["access_token"]
            print(f"Found Page: {page['name']} (id={page['id']})")
            break
    if not page_token:
        print(f"ERROR: Page id {page_id} not found in /me/accounts for this user.", file=sys.stderr)
        sys.exit(1)

    auth.save_facebook_token(page_id=page_id, page_token=page_token)
    print(f"Saved Page Token to {auth.facebook_token_path()}")


def whoami() -> None:
    cfg = auth.load_facebook_config()
    r = requests.get(
        f"{GRAPH_API}/{cfg.page_id}",
        params={"access_token": cfg.page_token, "fields": "name,id"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    print(f"Page: {data['name']}  (id={data['id']})")


def main():
    parser = argparse.ArgumentParser(prog="python -m src.publishers.facebook")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_setup = sub.add_parser("setup", help="One-time: exchange user token for long-lived page token")
    p_setup.add_argument("--user-token", required=True, help="Short-lived user access token from Graph API Explorer")

    sub.add_parser("whoami", help="Show configured Page")

    args = parser.parse_args()
    if args.cmd == "setup":
        setup(args.user_token)
    elif args.cmd == "whoami":
        whoami()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Smoke-test the CLI**

Run: `python -m src.publishers.facebook whoami`
Expected: Helpful error pointing to the setup command (because token not configured yet).

- [ ] **Step 8: Commit**

```bash
git add src/publishers/auth.py src/publishers/facebook.py tests/test_publishers_base.py .env.example
git commit -m "feat: Facebook config storage + setup CLI"
```

---

## Task 7: Facebook upload — 3-phase Graph API video upload

**Files:**
- Modify: `src/publishers/facebook.py` (add `upload()`)
- Create: `tests/test_publishers_facebook.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_publishers_facebook.py`:

```python
"""Tests for Facebook upload — all HTTP calls mocked."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def work_dir(tmp_path):
    (tmp_path / "youtube_metadata.json").write_text(
        (FIXTURES / "youtube_metadata.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    video = tmp_path / "dubbed_video.mp4"
    video.write_bytes(b"\x00" * 10_000)
    return tmp_path


@pytest.fixture
def fake_cfg():
    from src.publishers.auth import FacebookConfig
    return FacebookConfig(page_id="999", page_token="EAAB_fake")


def _post_responses(start_resp, transfer_resp, finish_resp):
    """Build a side_effect list for requests.post: start → transfer chunks → finish."""
    def make(json_payload, status=200):
        m = MagicMock()
        m.status_code = status
        m.json.return_value = json_payload
        m.raise_for_status = MagicMock()
        return m
    # one transfer call in our mock; production code may make many
    return [make(start_resp), make(transfer_resp), make(finish_resp)]


def test_upload_happy_path_returns_video_url(work_dir, fake_cfg):
    from src.publishers import facebook as fb

    responses = _post_responses(
        start_resp={"upload_session_id": "SESS_1", "video_id": "V_1",
                    "start_offset": "0", "end_offset": "10000"},
        transfer_resp={"start_offset": "10000", "end_offset": "10000"},
        finish_resp={"success": True, "video_id": "V_1"},
    )

    with patch.object(fb.auth, "load_facebook_config", return_value=fake_cfg), \
         patch.object(fb.requests, "post", side_effect=responses) as mock_post:
        result = fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is True
    assert result.platform == "facebook"
    assert result.video_id == "V_1"
    assert "facebook.com" in result.url

    finish_call = mock_post.call_args_list[-1]
    finish_data = finish_call.kwargs["data"]
    assert finish_data["upload_phase"] == "finish"
    assert finish_data["published"] is False
    assert finish_data["unpublished_content_type"] == "DRAFT"


def test_upload_public_publishes_immediately(work_dir, fake_cfg):
    from src.publishers import facebook as fb

    responses = _post_responses(
        start_resp={"upload_session_id": "S", "video_id": "V",
                    "start_offset": "0", "end_offset": "10000"},
        transfer_resp={"start_offset": "10000", "end_offset": "10000"},
        finish_resp={"success": True, "video_id": "V"},
    )
    with patch.object(fb.auth, "load_facebook_config", return_value=fake_cfg), \
         patch.object(fb.requests, "post", side_effect=responses) as mock_post:
        fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=True)

    finish_data = mock_post.call_args_list[-1].kwargs["data"]
    assert finish_data["published"] is True
    assert "unpublished_content_type" not in finish_data


def test_upload_token_expired_returns_actionable_error(work_dir, fake_cfg):
    from src.publishers import facebook as fb

    err_resp = MagicMock()
    err_resp.status_code = 400
    err_resp.json.return_value = {"error": {"code": 190, "message": "Invalid OAuth token"}}
    err_resp.raise_for_status = MagicMock()

    with patch.object(fb.auth, "load_facebook_config", return_value=fake_cfg), \
         patch.object(fb.requests, "post", return_value=err_resp):
        result = fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is False
    assert result.error == "auth_expired"
    assert "setup" in result.error_message.lower()


def test_upload_not_logged_in_returns_failure(work_dir):
    from src.publishers import facebook as fb
    from src.publishers.auth import NotLoggedInError

    with patch.object(fb.auth, "load_facebook_config", side_effect=NotLoggedInError("no cfg")):
        result = fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)
    assert result.success is False
    assert result.error == "auth_not_logged_in"
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_publishers_facebook.py -v`
Expected: All 4 tests fail because `upload()` does not exist.

- [ ] **Step 3: Implement upload() in facebook.py**

Append to `src/publishers/facebook.py` (after the existing helpers, before `main()`):

```python
import json as _json

from src.publishers.base import PublishResult


GRAPH_VIDEO_API = "https://graph-video.facebook.com/v21.0"


def _load_metadata(work_dir: str) -> dict:
    path = os.path.join(work_dir, "youtube_metadata.json")
    if not os.path.exists(path):
        return {"title": "Video", "description": ""}
    with open(path, encoding="utf-8") as f:
        return _json.load(f)


def _classify_graph_error(payload: dict) -> tuple[str, str, bool]:
    """Map Graph API error JSON to (code, message, retryable)."""
    err = payload.get("error", {}) if isinstance(payload, dict) else {}
    fb_code = err.get("code")
    fb_msg = err.get("message", "Facebook API error")

    if fb_code == 190:
        return ("auth_expired",
                "Facebook page token is no longer valid. Run setup again: "
                "python -m src.publishers.facebook setup --user-token <SHORT_LIVED_TOKEN>",
                False)
    if fb_code == 200:
        return ("auth_permission_denied",
                f"Permission denied. Re-grant pages_manage_posts. ({fb_msg})",
                False)
    if fb_code in (4, 17, 32, 613):
        return ("rate_limited", f"Rate limited by Facebook. ({fb_msg})", True)
    if fb_code == 100:
        return ("validation_failed", f"Invalid parameter: {fb_msg}", False)
    return ("unknown", fb_msg, False)


def upload(work_dir: str, video_path: str, public: bool = False) -> PublishResult:
    """Upload dubbed video to Facebook Page. Never raises — returns PublishResult."""
    try:
        cfg = auth.load_facebook_config()
    except auth.NotLoggedInError as e:
        return PublishResult(
            platform="facebook", success=False,
            error="auth_not_logged_in", error_message=str(e), retryable=False,
        )

    metadata = _load_metadata(work_dir)
    title = metadata.get("title", "Video")[:255]
    description = f"{metadata.get('title', '')}\n\n{metadata.get('description', '')}".strip()[:8000]

    file_size = os.path.getsize(video_path)
    url = f"{GRAPH_VIDEO_API}/{cfg.page_id}/videos"

    # Phase 1: start
    r = requests.post(url, data={
        "upload_phase": "start",
        "file_size": file_size,
        "access_token": cfg.page_token,
    }, timeout=60)
    start_payload = r.json()
    if r.status_code >= 400 or "error" in start_payload:
        code, msg, retryable = _classify_graph_error(start_payload)
        return PublishResult(platform="facebook", success=False, error=code,
                             error_message=msg, retryable=retryable)
    session_id = start_payload["upload_session_id"]

    # Phase 2: transfer chunks
    with open(video_path, "rb") as f:
        start_offset = int(start_payload["start_offset"])
        end_offset = int(start_payload["end_offset"])
        while start_offset < end_offset:
            f.seek(start_offset)
            chunk = f.read(end_offset - start_offset)
            r = requests.post(url, data={
                "upload_phase": "transfer",
                "upload_session_id": session_id,
                "start_offset": start_offset,
                "access_token": cfg.page_token,
            }, files={"video_file_chunk": chunk}, timeout=300)
            payload = r.json()
            if r.status_code >= 400 or "error" in payload:
                code, msg, retryable = _classify_graph_error(payload)
                return PublishResult(platform="facebook", success=False, error=code,
                                     error_message=msg, retryable=retryable)
            start_offset = int(payload["start_offset"])
            end_offset = int(payload["end_offset"])

    # Phase 3: finish
    finish_data = {
        "upload_phase": "finish",
        "upload_session_id": session_id,
        "title": title,
        "description": description,
        "published": public,
        "access_token": cfg.page_token,
    }
    if not public:
        finish_data["unpublished_content_type"] = "DRAFT"

    r = requests.post(url, data=finish_data, timeout=120)
    payload = r.json()
    if r.status_code >= 400 or "error" in payload:
        code, msg, retryable = _classify_graph_error(payload)
        return PublishResult(platform="facebook", success=False, error=code,
                             error_message=msg, retryable=retryable)

    video_id = payload.get("video_id") or start_payload.get("video_id")
    return PublishResult(
        platform="facebook", success=True,
        video_id=video_id,
        url=f"https://facebook.com/{video_id}",
    )
```

- [ ] **Step 4: Run FB tests, expect pass**

Run: `pytest tests/test_publishers_facebook.py -v`
Expected: 4 passed.

- [ ] **Step 5: Full regression**

Run: `pytest -q`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/publishers/facebook.py tests/test_publishers_facebook.py
git commit -m "feat: Facebook Page 3-phase resumable video upload"
```

---

## Task 8: Documentation — README Auto-Publish section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append the Auto-Publish section to README.md**

Locate the existing "## Sử dụng" section. Just before "## License", insert:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README — Auto-publish setup + usage"
```

---

## Task 9: End-to-end manual verification (optional, user-driven)

This task is not automated. After Task 1-8, user should:

- [ ] **Step 1: Setup YouTube credentials** (one-time, follow README)
- [ ] **Step 2: Run a dub + upload on a short test video**

```bash
python pipeline_vi.py --file input/short_test.mp4 --source-lang zh --voice male --upload youtube
```

Expected: pipeline finishes; final log shows `[OK] youtube: https://...`. Open the URL — video should be visible to you as `private` on your channel.

- [ ] **Step 3: Setup Facebook credentials** (one-time)
- [ ] **Step 4: Run dub + upload to both platforms**

```bash
python pipeline_vi.py --file input/short_test.mp4 --source-lang zh --voice male --upload youtube,facebook
```

Expected: log shows `[OK]` for both. Facebook video appears in Page's draft queue (not on timeline).

- [ ] **Step 5: Test fail isolation**

Temporarily corrupt `~/.auto-translate/youtube_token.json`, then run with `--upload youtube,facebook`. Expected: `[FAIL] youtube: auth_expired ...` followed by `[OK] facebook: ...`. Pipeline exits 0.

- [ ] **Step 6: Final push**

```bash
git push origin main
```

---

## Done criteria

- All 22 existing tests still pass + new tests pass (target: ~35 tests total)
- Both `pipeline_vi.py --help` and `pipeline.py --help` show `--upload` and `--public`
- `python -m src.publishers.youtube whoami` works after one-time login
- `python -m src.publishers.facebook whoami` works after one-time setup
- End-to-end smoke upload to private YouTube + draft Facebook video succeeds
- README explains setup + usage clearly enough that a fresh user can follow
- Repo has no leaked tokens (token files live in `~/.auto-translate/`, gitignored)
