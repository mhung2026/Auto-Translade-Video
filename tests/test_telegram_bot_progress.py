"""Tests for ProgressReporter — pure rendering + edit dispatch (mocked)."""
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class FakeJob:
    job_id: int = 7
    progress_message: MagicMock = field(default_factory=lambda: MagicMock(edit_text=AsyncMock()))


@pytest.mark.asyncio
async def test_start_renders_all_steps_pending():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    bot = MagicMock()
    reporter = ProgressReporter(bot, job)

    await reporter.start()

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "Job #7" in sent
    assert sent.count("·") == 11


@pytest.mark.asyncio
async def test_update_step_marks_step_ok():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("download", "ok")

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "✓ Download video" in sent


@pytest.mark.asyncio
async def test_update_step_running_uses_hourglass():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()
    reporter._min_edit_interval = 0

    await reporter.update_step("asr", "running")

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "⏳ ASR" in sent


@pytest.mark.asyncio
async def test_asr_step_shows_n_segments():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("asr", "ok", n_segments=12)

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "✓ ASR (speech-to-text) (12 segs)" in sent


@pytest.mark.asyncio
async def test_tts_shows_failed_count():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("tts", "ok", n_segments=10, n_failed=2)

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "(10 segs, 2 failed)" in sent


@pytest.mark.asyncio
async def test_upload_url_lands_in_finalize_footer():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("upload:youtube", "ok", url="https://youtu.be/abc")
    await reporter.update_step("upload:facebook", "ok", url="https://facebook.com/v_1")
    await reporter.finalize({"work_dir": "/tmp/x"})

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "✅ Job #7 DONE" in sent
    assert "🔗 youtube: https://youtu.be/abc" in sent
    assert "🔗 facebook: https://facebook.com/v_1" in sent


@pytest.mark.asyncio
async def test_upload_fail_shows_error_code_inline():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("upload:facebook", "fail", error="auth_expired")

    sent = job.progress_message.edit_text.call_args.args[0]
    assert "✗ Upload Facebook [auth_expired]" in sent


@pytest.mark.asyncio
async def test_unknown_step_silently_ignored():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("translate_pending", "ok", work_dir="/tmp/x")
    sent = job.progress_message.edit_text.call_args.args[0]
    assert "translate_pending" not in sent
    assert "/tmp/x" not in sent


@pytest.mark.asyncio
async def test_finalize_marks_remaining_pending_as_ok():
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()
    await reporter.update_step("download", "ok")

    await reporter.finalize({"work_dir": "/tmp/x"})

    sent = job.progress_message.edit_text.call_args.args[0]
    assert sent.count("·") == 0
