"""Tests for translate_via_claude — subprocess wrapper, all I/O mocked."""
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _force_unix_platform(monkeypatch):
    """Tests assume the create_subprocess_exec branch.

    On Windows production code routes through create_subprocess_shell to
    handle the `claude.cmd` npm wrapper; pretend we are on Linux during tests
    so the assertions remain stable regardless of host OS.
    """
    monkeypatch.setattr("sys.platform", "linux")


def _make_workdir(tmp_path: Path, with_transcript_vi: bool = False) -> Path:
    wd = tmp_path / "wd"
    wd.mkdir()
    (wd / "transcript_original.json").write_text(json.dumps([{"id": 1, "text": "hi"}]))
    if with_transcript_vi:
        (wd / "transcript_vi.json").write_text(json.dumps([{"id": 1, "text": "hi", "text_vi": "chào"}]))
    return wd


@pytest.mark.asyncio
async def test_skips_when_transcript_vi_already_exists(tmp_path):
    from src.telegram_bot import translator

    wd = _make_workdir(tmp_path, with_transcript_vi=True)
    cancel = asyncio.Event()

    with patch("asyncio.create_subprocess_exec") as spawn:
        await translator.translate_via_claude(wd, cwd=tmp_path, cancel_event=cancel)
        spawn.assert_not_called()


@pytest.mark.asyncio
async def test_success_when_subprocess_zero_and_file_appears(tmp_path):
    from src.telegram_bot import translator

    wd = _make_workdir(tmp_path)
    cancel = asyncio.Event()
    expected_out = wd / "transcript_vi.json"

    proc = MagicMock()
    proc.returncode = 0

    async def fake_communicate():
        expected_out.write_text("[]")
        return (b"done", b"")

    proc.communicate = fake_communicate
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        await translator.translate_via_claude(wd, cwd=tmp_path, cancel_event=cancel)

    assert expected_out.exists()


@pytest.mark.asyncio
async def test_raises_when_subprocess_nonzero(tmp_path):
    from src.telegram_bot import translator

    wd = _make_workdir(tmp_path)
    cancel = asyncio.Event()

    proc = MagicMock()
    proc.returncode = 2

    async def fake_communicate():
        return (b"", b"claude error: not authenticated")

    proc.communicate = fake_communicate
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(translator.TranslateError) as exc:
            await translator.translate_via_claude(wd, cwd=tmp_path, cancel_event=cancel)
    assert "exited 2" in str(exc.value)
    assert "not authenticated" in str(exc.value)


@pytest.mark.asyncio
async def test_raises_when_transcript_not_created(tmp_path):
    from src.telegram_bot import translator

    wd = _make_workdir(tmp_path)
    cancel = asyncio.Event()

    proc = MagicMock()
    proc.returncode = 0

    async def fake_communicate():
        return (b"all done", b"")

    proc.communicate = fake_communicate
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(translator.TranslateError) as exc:
            await translator.translate_via_claude(wd, cwd=tmp_path, cancel_event=cancel)
    assert "transcript_vi.json not found" in str(exc.value)


@pytest.mark.asyncio
async def test_timeout_kills_subprocess(tmp_path):
    from src.telegram_bot import translator

    wd = _make_workdir(tmp_path)
    cancel = asyncio.Event()

    proc = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    async def fake_communicate():
        await asyncio.sleep(10)
        return (b"", b"")

    proc.communicate = fake_communicate

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(translator.TranslateError) as exc:
            await translator.translate_via_claude(
                wd, cwd=tmp_path, cancel_event=cancel, timeout_sec=0,
            )
    assert "timed out" in str(exc.value).lower()
    proc.kill.assert_called()


@pytest.mark.asyncio
async def test_cancel_event_terminates_subprocess(tmp_path):
    from src.telegram_bot import translator

    wd = _make_workdir(tmp_path)
    cancel = asyncio.Event()

    proc = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    comm_future = asyncio.Future()

    async def fake_communicate():
        return await comm_future

    proc.communicate = fake_communicate

    async def trip_cancel():
        await asyncio.sleep(0.05)
        cancel.set()
        await asyncio.sleep(0.05)
        if not comm_future.done():
            comm_future.set_result((b"", b""))

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with pytest.raises(asyncio.CancelledError):
            await asyncio.gather(
                translator.translate_via_claude(wd, cwd=tmp_path, cancel_event=cancel),
                trip_cancel(),
            )
    proc.terminate.assert_called()
