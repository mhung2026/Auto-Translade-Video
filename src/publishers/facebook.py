"""Facebook Page publisher — setup + whoami CLI (upload comes in Task 7).

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


# Real upload() implementation lands in Task 7. This stub keeps Task 4's
# dispatcher tests passing (`importlib.import_module("src.publishers.facebook")`
# must succeed and `module.upload` must exist).
def upload(work_dir: str, video_path: str, public: bool = False):
    raise NotImplementedError(
        "Facebook publisher not yet implemented. See Task 7 of the plan."
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
