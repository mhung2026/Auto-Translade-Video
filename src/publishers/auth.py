"""Token storage / refresh helpers shared between publisher modules.

Storage location:
  ~/.auto-translate/
  ├── youtube_client_secrets.json   (user-provided)
  ├── youtube_token.json            (auto-generated after login)
  └── facebook_token.json           (auto-generated after setup)

Override the parent directory via env var AUTO_TRANSLATE_HOME.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path


def auto_translate_home() -> Path:
    """Return the directory holding publisher credentials. Create if missing."""
    override = os.environ.get("AUTO_TRANSLATE_HOME")
    home = Path(override) if override else Path.home() / ".auto-translate"
    home.mkdir(parents=True, exist_ok=True)
    return home


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
