"""Background worker — consumes one job at a time from an asyncio queue.

A 'job' is one video link → dub → upload sequence. Jobs run sequentially:
LucyLab single-export and Demucs CPU usage make parallelism unsafe.
"""
import asyncio
import logging
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from telegram import Bot, Message

from src.telegram_bot.progress import ProgressReporter
from src.telegram_bot.translator import translate_via_claude

logger = logging.getLogger(__name__)


@dataclass
class Job:
    job_id: int
    url: str
    chat_id: int
    progress_message: Message
    work_dir: Path | None = None
    state: str = "queued"
    current_step: str = ""
    error: str | None = None
    enqueued_at: float = field(default_factory=time.time)


class Worker:
    def __init__(self, bot: Bot, claude_cwd: Path, work_dir_base: Path):
        self.bot = bot
        self.claude_cwd = claude_cwd
        self.work_dir_base = work_dir_base
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.current: Job | None = None
        self._next_id = 1
        self._cancel_event = asyncio.Event()
        self._lock = asyncio.Lock()

    async def enqueue(self, url: str, chat_id: int, message: Message) -> int:
        async with self._lock:
            job_id = self._next_id
            self._next_id += 1
        reply = await message.reply_text(
            f"Job #{job_id} queued (position {self.queue.qsize() + 1})"
        )
        job = Job(job_id=job_id, url=url, chat_id=chat_id, progress_message=reply)
        await self.queue.put(job)
        return job_id

    def status_summary(self) -> str:
        if self.current:
            return (
                f"Current: Job #{self.current.job_id} — {self.current.current_step or 'starting'}\n"
                f"Queue: {self.queue.qsize()} pending"
            )
        return f"Idle. Queue: {self.queue.qsize()} pending"

    def cancel_current(self) -> str:
        if not self.current:
            return "No job running."
        self._cancel_event.set()
        return f"Cancel signaled for Job #{self.current.job_id}. Wait for current step to finish."

    async def run(self):
        """Main worker loop. Runs forever until the process exits."""
        while True:
            job = await self.queue.get()
            self.current = job
            self._cancel_event.clear()
            job.state = "running"
            try:
                await self._run_job(job)
                job.state = "done"
            except asyncio.CancelledError:
                job.state = "cancelled"
                logger.info(f"Job #{job.job_id} cancelled by user")
            except Exception as e:
                job.state = "failed"
                job.error = f"{type(e).__name__}: {e}"
                logger.exception(f"Job #{job.job_id} crashed")
                await self._report_crash(job, e)
            finally:
                self.current = None
                self.queue.task_done()

    async def _run_job(self, job: Job):
        reporter = ProgressReporter(self.bot, job)
        await reporter.start()
        loop = asyncio.get_running_loop()

        def progress_cb(step: str, status: str, **info):
            job.current_step = step
            asyncio.run_coroutine_threadsafe(
                reporter.update_step(step, status, **info), loop,
            )

        from pipeline_vi import run_pipeline_vi

        # --- Phase 1: download → ASR → write TRANSLATE_PENDING ---
        result = await asyncio.to_thread(
            run_pipeline_vi,
            url=job.url,
            file_path=None,
            source_lang="zh",
            voice_id="male",
            skip_video=False,
            output_dir=str(self.work_dir_base),
            bg_mode="duck",
            bg_duck_db=-15.0,
            progress_callback=progress_cb,
        )
        if self._cancel_event.is_set():
            raise asyncio.CancelledError()
        if "work_dir" in result:
            job.work_dir = Path(result["work_dir"])

        # --- Translation via Claude Code subprocess ---
        if result.get("status") == "translate_pending":
            await reporter.update_step("translate", "running")
            await translate_via_claude(
                work_dir=job.work_dir, cwd=self.claude_cwd, cancel_event=self._cancel_event,
            )
            await reporter.update_step("translate", "ok")

            # --- Phase 2: TTS → merge → upload ---
            result = await asyncio.to_thread(
                run_pipeline_vi,
                url=None,
                file_path=None,
                source_lang="zh",
                voice_id="male",
                skip_video=False,
                output_dir=str(self.work_dir_base),
                resume_dir=str(job.work_dir),
                bg_mode="duck",
                bg_duck_db=-15.0,
                upload_platforms=["youtube", "facebook"],
                public=True,
                progress_callback=progress_cb,
            )

        if self._cancel_event.is_set():
            raise asyncio.CancelledError()

        await reporter.finalize(result)

    async def _report_crash(self, job: Job, exc: Exception):
        tb_short = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        text = (
            f"💥 Job #{job.job_id} FAILED at step `{job.current_step}`\n"
            f"Error: {tb_short}\n"
            f"Work dir: `{job.work_dir}`\n"
            f"Resume: `python pipeline_vi.py --resume {job.work_dir}`"
        )
        try:
            await job.progress_message.edit_text(text, parse_mode="Markdown")
        except Exception:
            try:
                await self.bot.send_message(job.chat_id, text, parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to deliver crash report to Telegram")
