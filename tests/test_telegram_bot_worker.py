"""Tests for Worker — enqueue/dequeue/run_job, mocking pipeline + translator."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_worker(tmp_path):
    from src.telegram_bot.worker import Worker
    return Worker(bot=MagicMock(), claude_cwd=tmp_path, work_dir_base=tmp_path / "out")


def _fake_reply_message():
    msg = MagicMock()
    msg.edit_text = AsyncMock()
    msg.reply_text = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))
    return msg


@pytest.mark.asyncio
async def test_enqueue_increments_job_id(tmp_path):
    w = _make_worker(tmp_path)
    m1 = _fake_reply_message()
    m2 = _fake_reply_message()
    id1 = await w.enqueue(url="http://x/1", chat_id=1, message=m1)
    id2 = await w.enqueue(url="http://x/2", chat_id=1, message=m2)
    assert id1 == 1 and id2 == 2
    assert w.queue.qsize() == 2


@pytest.mark.asyncio
async def test_status_summary_idle(tmp_path):
    w = _make_worker(tmp_path)
    assert "Idle" in w.status_summary()


@pytest.mark.asyncio
async def test_status_summary_with_current(tmp_path):
    from src.telegram_bot.worker import Job
    w = _make_worker(tmp_path)
    w.current = Job(job_id=5, url="x", chat_id=1, progress_message=MagicMock(), current_step="tts")
    summary = w.status_summary()
    assert "Job #5" in summary and "tts" in summary


@pytest.mark.asyncio
async def test_cancel_with_no_current_returns_helpful_message(tmp_path):
    w = _make_worker(tmp_path)
    assert "No job" in w.cancel_current()


@pytest.mark.asyncio
async def test_cancel_sets_event_and_returns_ack(tmp_path):
    from src.telegram_bot.worker import Job
    w = _make_worker(tmp_path)
    w.current = Job(job_id=5, url="x", chat_id=1, progress_message=MagicMock())
    msg = w.cancel_current()
    assert "Cancel signaled" in msg
    assert w._cancel_event.is_set()


@pytest.mark.asyncio
async def test_run_job_happy_path_phase1_translate_phase2(tmp_path):
    """End-to-end Worker._run_job with both pipeline calls + translator mocked."""
    from src.telegram_bot.worker import Job

    w = _make_worker(tmp_path)
    work_dir = tmp_path / "out" / "session1"
    work_dir.mkdir(parents=True)

    job = Job(job_id=1, url="http://x", chat_id=1, progress_message=MagicMock(edit_text=AsyncMock()))

    phase1_result = {"status": "translate_pending", "work_dir": str(work_dir)}
    phase2_result = {"status": "ok", "work_dir": str(work_dir),
                     "publish": {"youtube": {"success": True, "url": "https://yt/a"},
                                 "facebook": {"success": True, "url": "https://fb/b"}}}
    pipeline_mock = MagicMock(side_effect=[phase1_result, phase2_result])

    async def fake_translate(work_dir, cwd, cancel_event, **kw):
        return None

    with patch("pipeline_vi.run_pipeline_vi", pipeline_mock), \
         patch("src.telegram_bot.worker.translate_via_claude", side_effect=fake_translate):
        await w._run_job(job)

    assert pipeline_mock.call_count == 2
    first_kwargs = pipeline_mock.call_args_list[0].kwargs
    second_kwargs = pipeline_mock.call_args_list[1].kwargs
    assert first_kwargs.get("url") == "http://x"
    assert first_kwargs.get("resume_dir") is None
    assert second_kwargs.get("resume_dir") == str(work_dir)
    assert second_kwargs.get("upload_platforms") == ["youtube", "facebook"]
    assert second_kwargs.get("public") is True


@pytest.mark.asyncio
async def test_run_job_crash_in_phase1_reports_and_propagates(tmp_path):
    from src.telegram_bot.worker import Job

    w = _make_worker(tmp_path)
    job = Job(job_id=1, url="http://x", chat_id=1, progress_message=MagicMock(edit_text=AsyncMock()))

    def boom(*a, **kw):
        raise RuntimeError("downloader exploded")

    with patch("pipeline_vi.run_pipeline_vi", side_effect=boom):
        with pytest.raises(RuntimeError):
            await w._run_job(job)


@pytest.mark.asyncio
async def test_run_job_cancel_between_phases_raises_cancelled(tmp_path):
    from src.telegram_bot.worker import Job

    w = _make_worker(tmp_path)
    job = Job(job_id=1, url="http://x", chat_id=1, progress_message=MagicMock(edit_text=AsyncMock()))

    phase1_result = {"status": "translate_pending", "work_dir": str(tmp_path)}

    def fake_phase1(*a, **kw):
        w._cancel_event.set()
        return phase1_result

    with patch("pipeline_vi.run_pipeline_vi", side_effect=fake_phase1):
        with pytest.raises(asyncio.CancelledError):
            await w._run_job(job)
