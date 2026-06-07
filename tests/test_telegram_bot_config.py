"""Tests for src.telegram_bot.config — env loading + validation."""
import pytest


def test_required_token_missing_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_WHITELIST_USER_ID", "123")
    monkeypatch.chdir(tmp_path)

    from src.telegram_bot import config
    with pytest.raises(SystemExit) as exc:
        config.load_config()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "TELEGRAM_BOT_TOKEN" in err


def test_whitelist_user_id_must_be_int(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setenv("TELEGRAM_WHITELIST_USER_ID", "not_an_int")
    monkeypatch.chdir(tmp_path)

    from src.telegram_bot import config
    with pytest.raises(SystemExit) as exc:
        config.load_config()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "TELEGRAM_WHITELIST_USER_ID" in err and "integer" in err.lower()


def test_load_config_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake:token")
    monkeypatch.setenv("TELEGRAM_WHITELIST_USER_ID", "12345")
    monkeypatch.delenv("TELEGRAM_BOT_REPO_ROOT", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_WORK_DIR_BASE", str(tmp_path / "out"))
    monkeypatch.chdir(tmp_path)

    from src.telegram_bot import config
    cfg = config.load_config()
    assert cfg.bot_token == "fake:token"
    assert cfg.whitelist_user_id == 12345
    assert cfg.repo_root == tmp_path.resolve()
    assert cfg.work_dir_base == (tmp_path / "out").resolve()
    assert cfg.work_dir_base.exists()
