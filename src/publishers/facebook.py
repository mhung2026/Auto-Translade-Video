"""Facebook Page publisher — setup + whoami CLI (upload comes in Task 7).

CLI:
    python -m src.publishers.facebook setup --user-token <SHORT_LIVED>
        # exchanges for long-lived page token, stores it
    python -m src.publishers.facebook whoami
        # prints the configured Page name + id
"""
import argparse
import json
import os
import sys

import requests
from dotenv import load_dotenv

from src.publishers import auth
from src.publishers.base import PublishResult


GRAPH_API = "https://graph.facebook.com/v21.0"
GRAPH_VIDEO_API = "https://graph-video.facebook.com/v21.0"


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
    load_dotenv()                            # populate FACEBOOK_APP_ID etc. without forcing config.py
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
    try:
        r.raise_for_status()
    except requests.HTTPError:
        # NOTE: never print the URL — query string holds client_secret + token.
        print(f"ERROR: Graph API returned {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
    try:
        long_user_token = r.json()["access_token"]
    except KeyError:
        print(f"ERROR: Unexpected Graph API response: {r.text}", file=sys.stderr)
        sys.exit(1)
    print("Long-lived user token acquired.")

    # Step 2: long-lived user token → page accounts → page-specific token
    r = requests.get(
        f"{GRAPH_API}/me/accounts",
        params={"access_token": long_user_token},
        timeout=30,
    )
    try:
        r.raise_for_status()
    except requests.HTTPError:
        # NOTE: never print the URL — query string holds the long-lived user token.
        print(f"ERROR: Graph API returned {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
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
    try:
        cfg = auth.load_facebook_config()
    except auth.NotLoggedInError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    r = requests.get(
        f"{GRAPH_API}/{cfg.page_id}",
        params={"access_token": cfg.page_token, "fields": "name,id"},
        timeout=30,
    )
    try:
        r.raise_for_status()
    except requests.HTTPError:
        # NOTE: never print the URL — query string holds the page access token.
        print(f"ERROR: Graph API returned {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
    try:
        data = r.json()
        print(f"Page: {data['name']}  (id={data['id']})")
    except KeyError:
        print(f"ERROR: Unexpected Graph API response: {r.text}", file=sys.stderr)
        sys.exit(1)


def _load_metadata(work_dir: str) -> dict:
    path = os.path.join(work_dir, "youtube_metadata.json")
    if not os.path.exists(path):
        return {"title": "Video", "description": ""}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    """Upload dubbed video to Facebook Page. Never raises — returns PublishResult.

    NOTE: We deliberately do NOT call r.raise_for_status() on Graph API responses.
    The HTTPError string includes the full request URL, which on Graph API calls
    can carry the access_token in the query string (depending on how the SDK was
    constructed). We use status_code + body JSON for error info instead.
    """
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
