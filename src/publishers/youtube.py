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
