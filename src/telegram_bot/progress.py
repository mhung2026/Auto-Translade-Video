"""Progress reporter — formats and edits the Telegram message in place."""
import asyncio
import logging
import time

from telegram import Bot
from telegram.error import RetryAfter, TimedOut

logger = logging.getLogger(__name__)


DISPLAY_STEPS = [
    ("download",       "Download video"),
    ("extract_audio",  "Extract audio"),
    ("vocal_sep",      "Separate BGM (Demucs)"),
    ("asr",            "ASR (speech-to-text)"),
    ("translate",      "Translate (Claude)"),
    ("tts",            "TTS Vietnamese"),
    ("merge_audio",    "Mix audio + BGM"),
    ("merge_video",    "Render final video"),
    ("metadata",       "Generate YT metadata"),
    ("upload:youtube", "Upload YouTube"),
    ("upload:facebook","Upload Facebook"),
]
DISPLAY_KEYS = {key for key, _ in DISPLAY_STEPS}

ICON = {"running": "⏳", "ok": "✓", "fail": "✗", "pending": "·"}


class ProgressReporter:
    def __init__(self, bot: Bot, job):
        self.bot = bot
        self.job = job
        self.step_status: dict[str, str] = {s[0]: "pending" for s in DISPLAY_STEPS}
        self.step_info: dict[str, dict] = {}
        self._last_edit = 0.0
        self._min_edit_interval = 1.0

    async def start(self):
        await self._edit(self._render(header=f"Job #{self.job.job_id} — starting"))

    async def update_step(self, step: str, status: str, **info):
        if step not in DISPLAY_KEYS:
            logger.debug(f"ignoring unknown step name: {step}")
            return
        self.step_status[step] = status
        if info:
            self.step_info[step] = info

        now = time.time()
        if status == "running" and (now - self._last_edit) < self._min_edit_interval:
            return
        await self._edit(self._render())
        self._last_edit = now

    async def finalize(self, result: dict):
        for step in self.step_status:
            if self.step_status[step] == "pending":
                self.step_status[step] = "ok"
        urls = self._collect_upload_urls()
        footer = ""
        if urls:
            footer = "\n\n" + "\n".join(f"🔗 {p}: {u}" for p, u in urls.items())
        await self._edit(self._render(header=f"✅ Job #{self.job.job_id} DONE") + footer)

    def _render(self, header: str | None = None) -> str:
        lines = [header or f"Job #{self.job.job_id} — running"]
        for step_key, label in DISPLAY_STEPS:
            status = self.step_status[step_key]
            icon = ICON[status]
            info = self.step_info.get(step_key, {})
            extra = ""
            if step_key == "asr" and "n_segments" in info:
                extra = f" ({info['n_segments']} segs)"
            elif step_key == "tts" and "n_segments" in info:
                failed = info.get("n_failed", 0)
                extra = f" ({info['n_segments']} segs" + (f", {failed} failed" if failed else "") + ")"
            elif step_key.startswith("upload:") and status == "fail" and "error" in info:
                extra = f" [{info['error']}]"
            lines.append(f"{icon} {label}{extra}")
        return "\n".join(lines)

    def _collect_upload_urls(self) -> dict[str, str]:
        urls = {}
        for step_key, info in self.step_info.items():
            if step_key.startswith("upload:") and info.get("url"):
                platform = step_key.split(":", 1)[1]
                urls[platform] = info["url"]
        return urls

    async def _edit(self, text: str):
        try:
            await self.job.progress_message.edit_text(text)
        except RetryAfter as e:
            logger.warning(f"Telegram rate limit, sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except TimedOut:
            pass
        except Exception as e:
            logger.warning(f"Failed to edit progress message: {e}")
