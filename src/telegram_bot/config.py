"""Telegram bot config — loaded from .env, no config.py dependency."""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class BotConfig:
    bot_token: str
    whitelist_user_id: int
    repo_root: Path
    work_dir_base: Path


def _required(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(
            f"ERROR: {key} not set. Add it to .env (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)
    return val


def load_config() -> BotConfig:
    load_dotenv()

    bot_token = _required("TELEGRAM_BOT_TOKEN")
    raw_user_id = _required("TELEGRAM_WHITELIST_USER_ID")
    try:
        whitelist_user_id = int(raw_user_id)
    except ValueError:
        print(
            "ERROR: TELEGRAM_WHITELIST_USER_ID must be an integer.",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = Path(os.environ.get("TELEGRAM_BOT_REPO_ROOT") or Path.cwd()).resolve()
    work_dir_base = Path(os.environ.get("TELEGRAM_BOT_WORK_DIR_BASE", "output/VN")).resolve()
    work_dir_base.mkdir(parents=True, exist_ok=True)

    return BotConfig(
        bot_token=bot_token,
        whitelist_user_id=whitelist_user_id,
        repo_root=repo_root,
        work_dir_base=work_dir_base,
    )
