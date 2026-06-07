"""Tests for src.content_via_claude — Claude Code subprocess + Higgsfield."""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_workdir_with_transcript(tmp_path: Path) -> Path:
    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "transcript_vi.json").write_text(
        json.dumps([
            {"id": 1, "text": "你好", "text_vi": "xin chào", "start": 0, "end": 1, "duration": 1}
        ]),
        encoding="utf-8",
    )
    # Pretend the repo root contains pipeline_vi.py
    (tmp_path / "pipeline_vi.py").write_text("# stub")
    return wd


def _make_workdir_with_metadata(tmp_path: Path) -> Path:
    wd = _make_workdir_with_transcript(tmp_path)
    (wd / "youtube_metadata.json").write_text(
        json.dumps({"title": "T", "description": "D", "hashtags": ["#a"]}),
        encoding="utf-8",
    )
    return wd


def test_generate_metadata_skips_if_output_exists(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude

    wd = _make_workdir_with_metadata(tmp_path)
    with patch("subprocess.run") as run:
        out = generate_metadata_via_claude(str(wd))
    run.assert_not_called()
    assert out == (wd / "youtube_metadata.json").resolve()


def test_generate_metadata_raises_when_transcript_missing(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude, ContentError

    wd = tmp_path / "wd"
    wd.mkdir()
    with pytest.raises(ContentError) as exc:
        generate_metadata_via_claude(str(wd))
    assert "transcript_vi.json" in str(exc.value)


def test_generate_metadata_happy_path(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude

    wd = _make_workdir_with_transcript(tmp_path)
    expected_out = wd / "youtube_metadata.json"

    def fake_run(cmd, **kwargs):
        # Simulate Claude writing the metadata file
        expected_out.write_text(
            json.dumps({"title": "Generated", "description": "Desc", "hashtags": ["#x"]}),
            encoding="utf-8",
        )
        result = MagicMock()
        result.returncode = 0
        result.stdout = "done"
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        out = generate_metadata_via_claude(str(wd))

    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["title"] == "Generated"


def test_generate_metadata_raises_when_subprocess_fails(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude, ContentError

    wd = _make_workdir_with_transcript(tmp_path)

    def fake_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 2
        result.stdout = ""
        result.stderr = "claude not authenticated"
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ContentError) as exc:
            generate_metadata_via_claude(str(wd))
    assert "exited 2" in str(exc.value)
    assert "not authenticated" in str(exc.value)


def test_generate_metadata_raises_when_file_not_created(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude, ContentError

    wd = _make_workdir_with_transcript(tmp_path)

    def fake_run(cmd, **kwargs):
        # Don't write any file
        result = MagicMock()
        result.returncode = 0
        result.stdout = "I'm done"
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(ContentError) as exc:
            generate_metadata_via_claude(str(wd))
    assert "not created" in str(exc.value)


def test_generate_metadata_raises_when_claude_cli_missing(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude, ContentError

    wd = _make_workdir_with_transcript(tmp_path)

    with patch("subprocess.run", side_effect=FileNotFoundError("claude")):
        with pytest.raises(ContentError) as exc:
            generate_metadata_via_claude(str(wd))
    assert "claude CLI not found" in str(exc.value)


def test_generate_metadata_timeout(tmp_path):
    from src.content_via_claude import generate_metadata_via_claude, ContentError

    wd = _make_workdir_with_transcript(tmp_path)

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)):
        with pytest.raises(ContentError) as exc:
            generate_metadata_via_claude(str(wd), timeout_sec=1)
    assert "timed out" in str(exc.value).lower()


def test_generate_thumbnail_skips_if_output_exists(tmp_path):
    from src.content_via_claude import generate_thumbnail_via_claude

    wd = _make_workdir_with_metadata(tmp_path)
    (wd / "thumbnail.jpg").write_bytes(b"\xff\xd8\xff\xe0fake")

    with patch("subprocess.run") as run:
        out = generate_thumbnail_via_claude(str(wd))
    run.assert_not_called()
    assert out == (wd / "thumbnail.jpg").resolve()


def test_generate_thumbnail_raises_when_metadata_missing(tmp_path):
    from src.content_via_claude import generate_thumbnail_via_claude, ContentError

    wd = _make_workdir_with_transcript(tmp_path)
    # no metadata file
    with pytest.raises(ContentError) as exc:
        generate_thumbnail_via_claude(str(wd))
    assert "youtube_metadata.json" in str(exc.value)


def test_generate_thumbnail_happy_path(tmp_path):
    from src.content_via_claude import generate_thumbnail_via_claude

    wd = _make_workdir_with_metadata(tmp_path)
    expected_out = wd / "thumbnail.jpg"

    def fake_run(cmd, **kwargs):
        expected_out.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        result = MagicMock()
        result.returncode = 0
        result.stdout = "done"
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        out = generate_thumbnail_via_claude(str(wd))

    assert out.exists()
    assert out.stat().st_size > 0
