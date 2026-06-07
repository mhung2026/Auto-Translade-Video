"""YouTube publisher — upload video + login CLI.

CLI:
    python -m src.publishers.youtube login    # one-time OAuth flow
    python -m src.publishers.youtube whoami   # show authorized channel
"""
import argparse
import json
import os
import sys

from src.publishers import auth
from src.publishers.base import PublishResult


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
