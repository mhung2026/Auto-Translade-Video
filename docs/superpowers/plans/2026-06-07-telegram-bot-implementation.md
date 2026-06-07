# Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that, given a video URL from the whitelisted user, autonomously runs the existing dub pipeline (download → ASR → translate via Claude Code subprocess → TTS → merge → upload public to YouTube + Facebook), and reports per-step progress by editing a single Telegram message.

**Architecture:** New `src/telegram_bot/` package with 5 focused modules (config, progress, translator, worker, bot). Pipeline gains a single optional `progress_callback` kwarg. Worker drives the pipeline in `asyncio.to_thread`, invokes `claude -p` between phase 1 and phase 2, and updates a `ProgressReporter` that edits one Telegram message in place. In-memory `asyncio.Queue`; sequential FIFO; whitelist by user_id.

**Tech Stack:** `python-telegram-bot[ext]>=21.0` (async, long-polling), `pytest-asyncio>=0.23` for tests, existing `pipeline_vi.py` + `pipeline.py` (with one new kwarg), the existing `translate-video-segments` Claude Code skill invoked via the `claude` CLI.

**Reference spec:** `docs/superpowers/specs/2026-06-07-telegram-bot-design.md`

---

## File Structure

**Create:**
- `src/telegram_bot/__init__.py` — package docstring
- `src/telegram_bot/__main__.py` — `python -m src.telegram_bot` entry
- `src/telegram_bot/config.py` — `BotConfig` dataclass + `load_config()`
- `src/telegram_bot/progress.py` — `ProgressReporter` + `DISPLAY_STEPS` + `ICON`
- `src/telegram_bot/translator.py` — `translate_via_claude()` + `TranslateError`
- `src/telegram_bot/worker.py` — `Job` + `Worker` class
- `src/telegram_bot/bot.py` — handlers + `main()`
- `deploy/auto-translate-bot.service` — Linux systemd unit (committed, used later)
- `tests/test_telegram_bot_config.py`
- `tests/test_telegram_bot_progress.py`
- `tests/test_telegram_bot_translator.py`
- `tests/test_telegram_bot_worker.py`
- `tests/test_pipeline_callback.py`

**Modify:**
- `pipeline_vi.py` — add `progress_callback` kwarg + `_notify()` helper + per-step calls
- `pipeline.py` — symmetrically add the same
- `requirements.txt` — add `python-telegram-bot[ext]>=21.0`, `pytest-asyncio>=0.23`
- `.env.example` — add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WHITELIST_USER_ID`
- `README.md` — append Telegram bot section

---

## Task 1: Foundation — deps, config module, env example

**Files:**
- Create: `src/telegram_bot/__init__.py`
- Create: `src/telegram_bot/__main__.py`
- Create: `src/telegram_bot/config.py`
- Create: `tests/test_telegram_bot_config.py`
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add deps to requirements.txt**

Append after the existing `google-auth-httplib2>=0.2.0` line:

```
python-telegram-bot[ext]>=21.0
pytest-asyncio>=0.23
```

- [ ] **Step 2: Install deps**

Run: `pip install -r requirements.txt`
Expected: telegram + pytest-asyncio installed (along with their dependencies), no version conflicts.

- [ ] **Step 3: Append TELEGRAM_* keys to .env.example**

Append at the end of `.env.example`:

```
# Telegram bot (only needed if you run `python -m src.telegram_bot`)
# 1) Create a bot via @BotFather on Telegram, copy the token
# 2) Find your own user_id by messaging @userinfobot on Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WHITELIST_USER_ID=
# Optional overrides:
# TELEGRAM_BOT_REPO_ROOT=/abs/path/to/Auto-Translade-video
# TELEGRAM_BOT_WORK_DIR_BASE=/abs/path/to/output/VN
```

- [ ] **Step 4: Write the failing test for config**

Create `tests/test_telegram_bot_config.py`:

```python
"""Tests for src.telegram_bot.config — env loading + validation."""
import sys
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
    assert cfg.work_dir_base.exists()              # auto-created
```

- [ ] **Step 5: Run, expect failure**

Run: `pytest tests/test_telegram_bot_config.py -v`
Expected: ImportError on `src.telegram_bot.config` (package not yet created).

- [ ] **Step 6: Implement the package + config module**

Create `src/telegram_bot/__init__.py`:

```python
"""Telegram bot — remote-triggered dub pipeline.

Run: python -m src.telegram_bot
Spec: docs/superpowers/specs/2026-06-07-telegram-bot-design.md
"""
```

Create `src/telegram_bot/__main__.py`:

```python
"""Entry point for `python -m src.telegram_bot`."""
from src.telegram_bot.bot import main

if __name__ == "__main__":
    main()
```

Create `src/telegram_bot/config.py`:

```python
"""Telegram bot config — loaded from .env, no config.py dependency."""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class BotConfig:
    bot_token: str
    whitelist_user_id: int
    repo_root: Path
    work_dir_base: Path


def _required(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(
            f"ERROR: {key} not set. Add it to .env (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)
    return val


def load_config() -> BotConfig:
    load_dotenv()

    bot_token = _required("TELEGRAM_BOT_TOKEN")
    raw_user_id = _required("TELEGRAM_WHITELIST_USER_ID")
    try:
        whitelist_user_id = int(raw_user_id)
    except ValueError:
        print(
            "ERROR: TELEGRAM_WHITELIST_USER_ID must be an integer.",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = Path(os.environ.get("TELEGRAM_BOT_REPO_ROOT") or Path.cwd()).resolve()
    work_dir_base = Path(os.environ.get("TELEGRAM_BOT_WORK_DIR_BASE", "output/VN")).resolve()
    work_dir_base.mkdir(parents=True, exist_ok=True)

    return BotConfig(
        bot_token=bot_token,
        whitelist_user_id=whitelist_user_id,
        repo_root=repo_root,
        work_dir_base=work_dir_base,
    )
```

NOTE: `bot.py` does not yet exist (created in Task 6). `__main__.py` imports it for forward-compat. To avoid an ImportError when running tests for config alone, only test `config` (not `__main__`) in this task.

- [ ] **Step 7: Run tests, expect pass**

Run: `pytest tests/test_telegram_bot_config.py -v`
Expected: 3 passed.

- [ ] **Step 8: Run full suite to catch regressions**

Run: `pytest -q --ignore=tests/test_telegram_bot_translator.py --ignore=tests/test_telegram_bot_worker.py --ignore=tests/test_telegram_bot_progress.py`
Expected: 44 existing + 3 new = 47 passed. (Ignored files don't exist yet; the `--ignore` flags are defensive only.)

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .env.example src/telegram_bot/__init__.py src/telegram_bot/__main__.py src/telegram_bot/config.py tests/test_telegram_bot_config.py
git commit -m "feat(telegram): scaffold package + config loader"
```

---

## Task 2: Progress reporter (pure rendering, mocked Telegram I/O)

**Files:**
- Create: `src/telegram_bot/progress.py`
- Create: `tests/test_telegram_bot_progress.py`

- [ ] **Step 1: Write failing tests for ProgressReporter rendering**

Create `tests/test_telegram_bot_progress.py`:

```python
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
    assert sent.count("·") == 11        # 11 display steps, all pending


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
    # Force throttle off so the running edit fires
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
    """Pipeline emits `translate_pending` which the worker handles itself;
    the reporter must not blow up when it sees an unknown step name."""
    from src.telegram_bot.progress import ProgressReporter

    job = FakeJob()
    reporter = ProgressReporter(MagicMock(), job)
    await reporter.start()

    await reporter.update_step("translate_pending", "ok", work_dir="/tmp/x")
    # Should not raise, and should not add anything to the message
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
    assert sent.count("·") == 0          # no pending left
```

- [ ] **Step 2: Configure pytest-asyncio**

Append to existing `conftest.py` (or create `pytest.ini` / `pyproject.toml` config — simplest is conftest):

```python
# In conftest.py, add at the top:
import pytest_asyncio  # noqa: F401  ensures plugin is loaded
```

Also append to `conftest.py`:

```python
def pytest_collection_modifyitems(config, items):
    """Auto-mark async test functions as asyncio so we don't need explicit @pytest.mark.asyncio everywhere."""
    # Not strictly necessary if we use @pytest.mark.asyncio explicitly, but keeps things tidy.
    pass
```

(Keep the file minimal — the `@pytest.mark.asyncio` decorators in the test file are enough; the import line is what we actually need.)

- [ ] **Step 3: Run, expect failure**

Run: `pytest tests/test_telegram_bot_progress.py -v`
Expected: ImportError on `src.telegram_bot.progress`.

- [ ] **Step 4: Implement progress.py**

Create `src/telegram_bot/progress.py`:

```python
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
        self._min_edit_interval = 1.0   # max 1 edit/sec/job

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
```

- [ ] **Step 5: Run, expect pass**

Run: `pytest tests/test_telegram_bot_progress.py -v`
Expected: 9 passed.

- [ ] **Step 6: Full regression**

Run: `pytest -q --ignore=tests/test_telegram_bot_translator.py --ignore=tests/test_telegram_bot_worker.py`
Expected: 47 existing + 9 new = 56 passed.

- [ ] **Step 7: Commit**

```bash
git add src/telegram_bot/progress.py tests/test_telegram_bot_progress.py conftest.py
git commit -m "feat(telegram): progress reporter — render + edit-in-place"
```

---

## Task 3: Pipeline callback refactor

**Files:**
- Modify: `pipeline_vi.py`
- Modify: `pipeline.py`
- Create: `tests/test_pipeline_callback.py`

- [ ] **Step 1: Write failing regression tests for the callback contract**

Create `tests/test_pipeline_callback.py`:

```python
"""Regression tests for the new progress_callback kwarg on both pipelines.

We do NOT exercise the real pipeline end-to-end (it needs Azure/LucyLab/ffmpeg).
We exercise the contract by checking the helper that emits notifications.
"""
import pytest


def test_notify_does_nothing_when_callback_none():
    from pipeline_vi import _notify
    # Should not raise
    _notify(None, "download", "running")
    _notify(None, "download", "ok", video_path="/tmp/x.mp4")


def test_notify_calls_callback_with_step_status_and_kwargs():
    from pipeline_vi import _notify
    captured = []
    def cb(step, status, **info):
        captured.append((step, status, info))
    _notify(cb, "asr", "ok", n_segments=5)
    assert captured == [("asr", "ok", {"n_segments": 5})]


def test_notify_swallows_callback_exceptions():
    """A bad callback must not crash the pipeline."""
    from pipeline_vi import _notify
    def bad_cb(step, status, **info):
        raise RuntimeError("boom")
    # Should not raise
    _notify(bad_cb, "asr", "ok")


def test_pipeline_signature_accepts_progress_callback_kwarg():
    """run_pipeline_vi must accept progress_callback=None without TypeError."""
    import inspect
    from pipeline_vi import run_pipeline_vi
    sig = inspect.signature(run_pipeline_vi)
    assert "progress_callback" in sig.parameters
    assert sig.parameters["progress_callback"].default is None


def test_run_pipeline_signature_for_jp_also_has_callback():
    import inspect
    from pipeline import run_pipeline
    sig = inspect.signature(run_pipeline)
    assert "progress_callback" in sig.parameters
    assert sig.parameters["progress_callback"].default is None
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_pipeline_callback.py -v`
Expected: 5 failures — `_notify` doesn't exist in pipeline_vi, and `progress_callback` not in signature.

- [ ] **Step 3: Add `_notify` helper and `progress_callback` kwarg to pipeline_vi.py**

Open `pipeline_vi.py`. Below the existing `LANG_MAP = {...}` block (search for `LANG_MAP`), insert:

```python


def _notify(callback, step: str, status: str, **info) -> None:
    """Emit a progress notification, swallowing any callback error.

    Used by the Telegram bot worker; CLI mode passes callback=None.
    """
    if callback is None:
        return
    try:
        callback(step, status, **info)
    except Exception:
        logger.exception("progress_callback raised, ignoring")
```

Modify the `run_pipeline_vi` signature (search for `def run_pipeline_vi(`). Add a final kwarg:

```python
def run_pipeline_vi(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice_id: str,
    skip_video: bool,
    output_dir: str,
    resume_dir: str | None = None,
    bg_mode: str = "demucs",
    bg_duck_db: float = -12.0,
    upload_platforms: list[str] | None = None,
    public: bool = False,
    progress_callback=None,
) -> dict:
```

Inside `run_pipeline_vi`, at each existing `# --- Step N: ...` comment, wrap with notify calls. Add these lines IMMEDIATELY AFTER the relevant `logger.info("STEP X: ...")` line (so notify fires AT THE START of the step) and IMMEDIATELY BEFORE the next `# --- Step` block (so notify fires AT THE END):

For Step 1 (download), inside the existing block:
```python
    # --- Step 1: Download or use local file ---
    logger.info("=" * 60)
    logger.info("STEP 1: Acquiring video")
    _notify(progress_callback, "download", "running")
    video_path = _resolve_video(work_dir, url, file_path)
    logger.info(f"Video: {video_path}")
    _notify(progress_callback, "download", "ok", video_path=video_path)
```

For Step 2 (extract):
```python
    # --- Step 2: Extract audio ---
    logger.info("=" * 60)
    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        logger.info(f"STEP 2: Reusing existing extracted audio: {audio_path}")
        _notify(progress_callback, "extract_audio", "ok")
    else:
        logger.info("STEP 2: Extracting audio")
        _notify(progress_callback, "extract_audio", "running")
        extract_audio(video_path, audio_path)
        _notify(progress_callback, "extract_audio", "ok")
```

For Step 2.5 (vocal_sep — only when bg_mode=demucs):
```python
    if bg_mode == "demucs":
        logger.info("=" * 60)
        logger.info("STEP 2.5: Separating vocals from original audio (Demucs)")
        _notify(progress_callback, "vocal_sep", "running")
        sep = separate_vocals(audio_path, work_dir)
        background_path = sep.get("no_vocals")
        ...   # leave existing logic unchanged
        _notify(progress_callback, "vocal_sep", "ok")
```

For Step 3 (ASR), wrap the existing transcribe block:
```python
    # --- Step 3: Speech-to-Text (ASR) ---
    logger.info("=" * 60)
    if os.path.exists(transcript_orig_path):
        logger.info(f"STEP 3: Reusing existing transcript: {transcript_orig_path}")
        with open(transcript_orig_path, encoding="utf-8") as f:
            segments = json.load(f)
        _notify(progress_callback, "asr", "ok", n_segments=len(segments))
    else:
        logger.info("STEP 3: Transcribing audio (ASR)")
        _notify(progress_callback, "asr", "running")
        segments = transcribe(audio_path, lang_code)
        save_transcript(segments, transcript_orig_path)
        generate_srt(segments, os.path.join(work_dir, "transcript_original.srt"), text_field="text")
        _notify(progress_callback, "asr", "ok", n_segments=len(segments))
    logger.info(f"Transcribed {len(segments)} segments")
```

For Step 4 (translate), emit `translate_pending` when the pipeline returns early. Find the existing `_write_translate_pending_hint(...)` block and add a notify just before the return:

```python
    else:
        _write_translate_pending_hint(work_dir, "vi-VN", source_lang)
        logger.warning("Translation pending — see TRANSLATE_PENDING.txt in work dir")
        _notify(progress_callback, "translate_pending", "ok", work_dir=work_dir)
        return {"status": "translate_pending", "work_dir": work_dir}
```

For Step 5 (TTS), wrap the synthesize loop. After it ends, count any synthesis failures (look at existing logic; treat `seg.get("text_vi", "").strip() == ""` or whatever the existing failure-tracking convention is). For a safe minimum:
```python
    # --- Step 5: TTS for each segment (LucyLab API) ---
    logger.info("=" * 60)
    logger.info("STEP 5: Synthesizing Vietnamese audio (LucyLab TTS)")
    _notify(progress_callback, "tts", "running")
    seg_dir = ensure_dir(os.path.join(work_dir, "segments"))
    tts_results = []
    ...   # leave existing loop untouched
    n_failed = sum(1 for r in tts_results if not r.get("ok", True))
    _notify(progress_callback, "tts", "ok", n_segments=len(tts_results), n_failed=n_failed)
```

For Step 6 (merge_audio): wrap the segment merge block:
```python
    # --- Step 6: Slow down + Fit-to-timeline + Merge audio ---
    _notify(progress_callback, "merge_audio", "running")
    # ... existing 6a / 6b / 6c logic untouched
    _notify(progress_callback, "merge_audio", "ok")
```

For Step 7 (merge_video):
```python
    # --- Step 7: Merge video (optional) ---
    dubbed_video_path = None
    if not skip_video:
        logger.info("=" * 60)
        logger.info("STEP 7: Creating dubbed video")
        _notify(progress_callback, "merge_video", "running")
        dubbed_video_path = os.path.join(work_dir, "dubbed_video.mp4")
        merge_video(video_path, merged_audio_path, dubbed_video_path)
        _notify(progress_callback, "merge_video", "ok", video_path=dubbed_video_path)
```

For Step 8 (metadata):
```python
    # --- Step 8: Generate thumbnails + YouTube metadata ---
    content_result = {"thumbnails": [], "metadata": {}}
    if config.GOOGLE_API_KEY:
        logger.info("=" * 60)
        logger.info("STEP 8: Generating thumbnails & YouTube metadata")
        _notify(progress_callback, "metadata", "running")
        try:
            content_result = generate_content(...)   # existing call untouched
            _notify(progress_callback, "metadata", "ok")
        except Exception as e:
            logger.error(f"Content generation failed (non-fatal): {e}")
            _notify(progress_callback, "metadata", "fail", error=str(e)[:120])
```

For Step 9 (upload), inside the existing upload block, after each platform result:
```python
        for platform_name, res in publish_results.items():
            step_key = f"upload:{platform_name}"
            if res.success:
                logger.info(f"  [OK] {platform_name}: {res.url}")
                _notify(progress_callback, step_key, "ok", url=res.url)
            else:
                logger.error(f"  [FAIL] {platform_name}: {res.error} - {res.error_message}")
                _notify(progress_callback, step_key, "fail", error=res.error or "unknown")
```

- [ ] **Step 4: Repeat for pipeline.py (JP)**

Apply identical changes to `pipeline.py`:
1. Add `_notify` helper (paste the same function definition near the top, below `LANG_MAP`).
2. Add `progress_callback=None` to `run_pipeline()` signature.
3. Wrap each step the same way (download / extract_audio / vocal_sep / asr / translate_pending / tts / merge_audio / merge_video / metadata / upload:* — JP pipeline may not have all these steps; only wrap the ones that exist).

- [ ] **Step 5: Run, expect pass**

Run: `pytest tests/test_pipeline_callback.py -v`
Expected: 5 passed.

- [ ] **Step 6: Full regression — verify no existing test broken**

Run: `pytest -q --ignore=tests/test_telegram_bot_translator.py --ignore=tests/test_telegram_bot_worker.py`
Expected: 56 prior + 5 new = 61 passed.

- [ ] **Step 7: Commit**

```bash
git add pipeline_vi.py pipeline.py tests/test_pipeline_callback.py
git commit -m "feat(pipeline): add progress_callback kwarg for bot integration"
```

---

## Task 4: Translator (Claude Code subprocess wrapper)

**Files:**
- Create: `src/telegram_bot/translator.py`
- Create: `tests/test_telegram_bot_translator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_telegram_bot_translator.py`:

```python
"""Tests for translate_via_claude — subprocess wrapper, all I/O mocked."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        # Simulate Claude writing the output file
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
    # communicate that never returns
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

    # communicate that hangs forever until we cancel
    comm_future = asyncio.Future()
    async def fake_communicate():
        return await comm_future
    proc.communicate = fake_communicate

    async def trip_cancel():
        await asyncio.sleep(0.05)
        cancel.set()
        # let _wait_with_cancel call terminate, then unblock communicate
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
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_telegram_bot_translator.py -v`
Expected: ImportError on `src.telegram_bot.translator`.

- [ ] **Step 3: Implement translator.py**

Create `src/telegram_bot/translator.py`:

```python
"""Wrapper around the Claude Code CLI for headless translation.

Requires:
- `claude` CLI installed (https://claude.com/claude-code)
- User logged into a paid Claude plan (Pro/Max) on this machine
- Skill `translate-video-segments` available in this repo's .claude/skills/
"""
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TranslateError(RuntimeError):
    pass


async def translate_via_claude(
    work_dir: Path,
    cwd: Path,
    cancel_event: asyncio.Event,
    timeout_sec: int = 600,
) -> None:
    """Invoke `claude -p` to run the translate-video-segments skill.

    Returns when transcript_vi.json exists in work_dir.
    Raises TranslateError on subprocess failure / timeout / missing output.
    Raises asyncio.CancelledError when cancel_event is set mid-run.
    """
    transcript_vi = work_dir / "transcript_vi.json"
    if transcript_vi.exists():
        logger.info(f"transcript_vi.json already exists at {transcript_vi}, skipping Claude")
        return

    prompt = (
        f"Use the translate-video-segments skill to translate the transcript at "
        f"{work_dir} from Chinese to Vietnamese. Read transcript_original.json, "
        f"write transcript_vi.json with a text_vi field added to each segment. "
        f"Do not run any other commands or ask follow-up questions."
    )
    cmd = ["claude", "-p", prompt, "--output-format", "text"]
    logger.info(f"Spawning Claude Code in cwd={cwd}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            _wait_with_cancel(proc, cancel_event), timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise TranslateError(f"Claude Code timed out after {timeout_sec}s")

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:500]
        raise TranslateError(f"Claude Code exited {proc.returncode}: {err}")

    if not transcript_vi.exists():
        out = stdout.decode("utf-8", errors="replace")[:500]
        raise TranslateError(
            f"Claude finished but transcript_vi.json not found. Output: {out}"
        )

    logger.info(f"Translation done: {transcript_vi}")


async def _wait_with_cancel(proc, cancel_event):
    """Race proc.communicate() against cancel_event.

    If cancel fires first: terminate the proc, wait up to 5s, kill if still alive,
    then raise CancelledError.
    """
    wait_task = asyncio.create_task(proc.communicate())
    cancel_task = asyncio.create_task(cancel_event.wait())

    done, pending = await asyncio.wait(
        {wait_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED,
    )

    if cancel_task in done:
        proc.terminate()
        try:
            await asyncio.wait_for(wait_task, timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
        raise asyncio.CancelledError()

    for p in pending:
        p.cancel()
    return wait_task.result()
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_telegram_bot_translator.py -v`
Expected: 6 passed.

- [ ] **Step 5: Full regression**

Run: `pytest -q --ignore=tests/test_telegram_bot_worker.py`
Expected: 61 prior + 6 new = 67 passed.

- [ ] **Step 6: Commit**

```bash
git add src/telegram_bot/translator.py tests/test_telegram_bot_translator.py
git commit -m "feat(telegram): Claude Code headless translator wrapper"
```

---

## Task 5: Worker (queue + run loop)

**Files:**
- Create: `src/telegram_bot/worker.py`
- Create: `tests/test_telegram_bot_worker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_telegram_bot_worker.py`:

```python
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
    from src.telegram_bot.worker import Job, Worker

    w = _make_worker(tmp_path)
    work_dir = tmp_path / "out" / "session1"
    work_dir.mkdir(parents=True)

    job = Job(job_id=1, url="http://x", chat_id=1, progress_message=MagicMock(edit_text=AsyncMock()))

    # Mock the two pipeline calls
    phase1_result = {"status": "translate_pending", "work_dir": str(work_dir)}
    phase2_result = {"status": "ok", "work_dir": str(work_dir),
                     "publish": {"youtube": {"success": True, "url": "https://yt/a"},
                                 "facebook": {"success": True, "url": "https://fb/b"}}}
    pipeline_mock = MagicMock(side_effect=[phase1_result, phase2_result])

    async def fake_translate(work_dir, cwd, cancel_event, **kw):
        return None

    with patch("src.telegram_bot.worker.run_pipeline_vi", pipeline_mock), \
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

    with patch("src.telegram_bot.worker.run_pipeline_vi", side_effect=boom):
        with pytest.raises(RuntimeError):
            await w._run_job(job)


@pytest.mark.asyncio
async def test_run_job_cancel_between_phases_raises_cancelled(tmp_path):
    from src.telegram_bot.worker import Job, Worker

    w = _make_worker(tmp_path)
    job = Job(job_id=1, url="http://x", chat_id=1, progress_message=MagicMock(edit_text=AsyncMock()))

    phase1_result = {"status": "translate_pending", "work_dir": str(tmp_path)}

    def fake_phase1(*a, **kw):
        w._cancel_event.set()
        return phase1_result

    with patch("src.telegram_bot.worker.run_pipeline_vi", side_effect=fake_phase1):
        with pytest.raises(asyncio.CancelledError):
            await w._run_job(job)
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest tests/test_telegram_bot_worker.py -v`
Expected: ImportError on `src.telegram_bot.worker`.

- [ ] **Step 3: Implement worker.py**

Create `src/telegram_bot/worker.py`:

```python
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
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest tests/test_telegram_bot_worker.py -v`
Expected: 8 passed.

- [ ] **Step 5: Full regression**

Run: `pytest -q`
Expected: 67 prior + 8 new = 75 passed.

- [ ] **Step 6: Commit**

```bash
git add src/telegram_bot/worker.py tests/test_telegram_bot_worker.py
git commit -m "feat(telegram): Worker — queue + sequential job runner"
```

---

## Task 6: Bot entry + handlers

**Files:**
- Create: `src/telegram_bot/bot.py`

No new tests for `bot.py` — it is glue around python-telegram-bot's `Application`. We rely on a manual smoke test instead. The worker, progress, translator, and config modules are already covered.

- [ ] **Step 1: Create bot.py**

Create `src/telegram_bot/bot.py`:

```python
"""Telegram bot main entry — registers handlers and starts long-polling.

Run: python -m src.telegram_bot
"""
import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from src.telegram_bot.config import load_config
from src.telegram_bot.worker import Worker

logger = logging.getLogger(__name__)


WELCOME = (
    "Bot ready. Send a Douyin/YouTube/TikTok link and I will dub it to Vietnamese, "
    "upload to YouTube + Facebook (PUBLIC), and report progress here.\n\n"
    "Commands:\n"
    "  /status — show queue + current job\n"
    "  /cancel — cancel current job (after current step finishes)\n"
    "  /help   — this message"
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ctx.bot_data["whitelist_user_id"]:
        logger.warning(f"Rejected /start from non-whitelist user_id={update.effective_user.id}")
        return
    await update.message.reply_text(WELCOME)


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ctx.bot_data["whitelist_user_id"]:
        return
    worker: Worker = ctx.bot_data["worker"]
    await update.message.reply_text(worker.status_summary())


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ctx.bot_data["whitelist_user_id"]:
        return
    worker: Worker = ctx.bot_data["worker"]
    await update.message.reply_text(worker.cancel_current())


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ctx.bot_data["whitelist_user_id"]:
        logger.warning(f"Rejected message from non-whitelist user_id={user_id}")
        return
    text = (update.message.text or "").strip()
    if not _looks_like_url(text):
        await update.message.reply_text("Send a video URL (Douyin/YouTube/TikTok).")
        return
    worker: Worker = ctx.bot_data["worker"]
    await worker.enqueue(
        url=text,
        chat_id=update.effective_chat.id,
        message=update.message,
    )


def _looks_like_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


async def _on_startup(app: Application):
    """Spawn the worker task after the Application is running."""
    worker: Worker = app.bot_data["worker"]
    asyncio.create_task(worker.run())
    logger.info("Worker task spawned")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config()

    app = (
        Application.builder()
        .token(cfg.bot_token)
        .post_init(_on_startup)
        .build()
    )
    worker = Worker(bot=app.bot, claude_cwd=cfg.repo_root, work_dir_base=cfg.work_dir_base)
    app.bot_data["whitelist_user_id"] = cfg.whitelist_user_id
    app.bot_data["worker"] = worker

    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info(f"Bot starting, whitelist user_id={cfg.whitelist_user_id}")
    app.run_polling()
```

- [ ] **Step 2: Smoke-test the entry point (no real bot token)**

Run: `python -m src.telegram_bot`
Expected: exit 1 with `ERROR: TELEGRAM_BOT_TOKEN not set...` (because .env has empty values).

- [ ] **Step 3: Full test regression**

Run: `pytest -q`
Expected: 75 passed (no new tests, just sanity).

- [ ] **Step 4: Commit**

```bash
git add src/telegram_bot/bot.py
git commit -m "feat(telegram): bot entry + handlers + worker spawn"
```

---

## Task 7: Deploy + README

**Files:**
- Create: `deploy/auto-translate-bot.service`
- Modify: `README.md`

- [ ] **Step 1: Create the Linux systemd unit**

Create `deploy/auto-translate-bot.service`:

```ini
[Unit]
Description=Auto-Translade Telegram Bot
After=network-online.target

[Service]
Type=simple
User=hai
WorkingDirectory=/home/hai/Auto-Translade-video
EnvironmentFile=/home/hai/Auto-Translade-video/.env
ExecStart=/home/hai/Auto-Translade-video/.venv/bin/python -m src.telegram_bot
Restart=on-failure
RestartSec=5s
StandardOutput=append:/var/log/auto-translate-bot.log
StandardError=append:/var/log/auto-translate-bot.log

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Append Telegram bot section to README.md**

Locate the existing `## Tự động đăng lên YouTube + Facebook Page` section (created in the auto-publish feature). After that section and before `## License`, insert:

```markdown
## Telegram bot — remote-triggered dub (server 24/7)

Cho phép bạn gửi link Douyin/YouTube/TikTok qua Telegram → bot tự download → dub → upload public lên YouTube + Facebook Page → báo từng bước thành công/thất bại về Telegram.

### Yêu cầu

- Tài khoản Claude trả phí (Pro/Max) + Claude Code CLI cài trên server (cho bước dịch tự động qua skill)
- Bot token Telegram (tạo qua [@BotFather](https://t.me/BotFather))
- User ID Telegram của bạn (hỏi [@userinfobot](https://t.me/userinfobot))

### Setup

1. Tạo bot Telegram qua @BotFather, copy token vào `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123:abc...
   TELEGRAM_WHITELIST_USER_ID=12345678
   ```
2. Cài `claude` CLI trên server và đăng nhập Claude Pro/Max.
3. Khởi chạy:
   ```bash
   python -m src.telegram_bot
   ```
4. Trên Telegram, gửi `/start` cho bot để xác nhận hoạt động.

### Sử dụng

- Gửi 1 URL bất kỳ → bot reply `Job #N queued`, sau đó edit liên tục 1 message để báo từng bước.
- `/status` — xem queue + job đang chạy
- `/cancel` — cancel job hiện tại (đợi step hiện tại kết thúc)

Mặc định: source language = `zh`, voice = `male`, bg-mode = `duck -15dB`, upload = `youtube + facebook`, privacy = `public`.

### Chạy 24/7

**Windows (NSSM, recommended):**
```
nssm install AutoTranslateBot
  Path:               C:\Path\To\Python\python.exe
  Arguments:          -m src.telegram_bot
  Startup directory:  C:\...\Auto-Translade-video
  I/O:                stdout/stderr → C:\Logs\bot.log
  Exit actions:       Restart (5s delay)
nssm start AutoTranslateBot
```

**Linux (systemd):**
```bash
sudo cp deploy/auto-translate-bot.service /etc/systemd/system/
sudo systemctl enable --now auto-translate-bot
sudo journalctl -u auto-translate-bot -f      # tail log
```

### Hành vi khi fail

Job fail giữa chừng → bot edit message:
```
💥 Job #N FAILED at step `tts`
Error: LucyLabError: TTS completed but no audio URL
Work dir: `output/VN/20260608121530_vi`
Resume: `python pipeline_vi.py --resume output/VN/20260608121530_vi`
```

Bot KHÔNG tự retry. Job tiếp theo trong queue vẫn chạy. Bạn SSH vào server và chạy lệnh `--resume` thủ công khi rảnh.
```

- [ ] **Step 3: Commit**

```bash
git add deploy/auto-translate-bot.service README.md
git commit -m "docs(telegram): deploy unit + README usage section"
```

---

## Task 8: End-to-end manual verification (user-driven)

This task is not automated — the user runs it after Tasks 1-7 land.

- [ ] **Step 1: Setup credentials**

Edit `.env`, fill `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WHITELIST_USER_ID`. Make sure `claude` CLI is in PATH and `claude whoami` works.

- [ ] **Step 2: Start bot in foreground for first test**

```bash
$env:PYTHONIOENCODING="utf-8"; python -m src.telegram_bot
```

Expected: `Bot starting, whitelist user_id=<your_id>` log line, no crash.

- [ ] **Step 3: Send `/start` from Telegram**

Expected: Welcome message reply.

- [ ] **Step 4: Send a short test video URL (≤15s clip)**

Expected: Bot replies `Job #1 queued (position 1)`, then edits the message every ~1 second with progress. Sequence:
- `⏳ Download video` → `✓ Download video`
- `⏳ Extract audio` → `✓ Extract audio`
- (vocal_sep skipped if bg_mode=duck — line stays `· Separate BGM` → goes `✓ Separate BGM` at finalize)
- `⏳ ASR (speech-to-text)` → `✓ ASR (speech-to-text) (N segs)`
- `⏳ Translate (Claude)` → (this can take 30-90s) → `✓ Translate (Claude)`
- `⏳ TTS Vietnamese` → `✓ TTS Vietnamese (N segs)`
- `⏳ Mix audio + BGM` → `✓ Mix audio + BGM`
- `⏳ Render final video` → `✓ Render final video`
- `⏳ Generate YT metadata` → `✓ Generate YT metadata`
- `⏳ Upload YouTube` → `✓ Upload YouTube`
- `⏳ Upload Facebook` → `✓ Upload Facebook`
- Final: `✅ Job #1 DONE` + URL footer

- [ ] **Step 5: Open the two URLs from the footer and confirm both videos exist (public)**

- [ ] **Step 6: Send a second URL while the first might still be running**

Expected: `Job #2 queued (position 2)` immediately, second job starts after first ends.

- [ ] **Step 7: Try `/cancel` mid-job (use a long video)**

Expected: `Cancel signaled for Job #N. Wait for current step to finish.` then after the current step the worker exits and the next job starts.

- [ ] **Step 8: Try `/status` while idle and while running**

Expected: appropriate summary.

- [ ] **Step 9: Install as service**

Use NSSM (Windows) per README. Verify the service starts on boot and survives a crash (kill the process; NSSM should respawn within 5s).

- [ ] **Step 10: Push the branch / merge to main**

```bash
git push
# or: git checkout main && git merge --ff-only feat/telegram-bot && git push origin main
```

---

## Done criteria

- 75 tests pass (44 prior + 31 new)
- `python -m src.telegram_bot` starts and responds to whitelisted user
- Sending a video URL produces a final DONE message with valid YouTube + Facebook URLs
- `/status` and `/cancel` work
- Service runner restarts the bot on crash (Windows NSSM verified; Linux systemd unit committed)
- README documents setup + commands + failure behavior
- No tokens / secrets reach Telegram chat or logs
