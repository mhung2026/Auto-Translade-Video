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
