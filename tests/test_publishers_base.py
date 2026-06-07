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
