import os
import pytest


def test_config_loads_env_vars(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "japaneast")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-20250514")
    monkeypatch.setenv("TTS_VOICE", "ja-JP-KeitaNeural")
    monkeypatch.setenv("TTS_MAX_SPEED_RATIO", "1.4")
    monkeypatch.setenv("DEFAULT_SOURCE_LANG", "en-US")
    monkeypatch.setenv("AUDIO_SAMPLE_RATE", "16000")
    monkeypatch.setenv("OUTPUT_DIR", "./output")

    import importlib
    import config
    importlib.reload(config)

    assert config.AZURE_SPEECH_KEY == "test-key"
    assert config.AZURE_SPEECH_REGION == "japaneast"
    assert config.ANTHROPIC_API_KEY == "sk-ant-test"
    assert config.ANTHROPIC_MODEL == "claude-opus-4-20250514"
    assert config.TTS_VOICE == "ja-JP-KeitaNeural"
    assert config.TTS_MAX_SPEED_RATIO == 1.4
    assert config.DEFAULT_SOURCE_LANG == "en-US"
    assert config.AUDIO_SAMPLE_RATE == 16000
    assert config.OUTPUT_DIR == "./output"


def test_config_defaults(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "japaneast")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("TTS_VOICE", raising=False)
    monkeypatch.delenv("TTS_MAX_SPEED_RATIO", raising=False)
    monkeypatch.delenv("DEFAULT_SOURCE_LANG", raising=False)
    monkeypatch.delenv("AUDIO_SAMPLE_RATE", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    import importlib
    import config
    importlib.reload(config)

    assert config.ANTHROPIC_MODEL == "claude-opus-4-20250514"
    assert config.TTS_VOICE == "ja-JP-KeitaNeural"
    assert config.TTS_MAX_SPEED_RATIO == 1.4
    assert config.DEFAULT_SOURCE_LANG == "en-US"
    assert config.AUDIO_SAMPLE_RATE == 16000
    assert config.OUTPUT_DIR == "./output"
