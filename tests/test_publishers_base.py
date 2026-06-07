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
