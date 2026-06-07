# Telegram Bot — Remote-Triggered Dub Pipeline Design Spec

**Date:** 2026-06-07
**Status:** Design approved, implementation pending
**Author:** Hai (Ho Quang Hai)

## 1. Goal

Run the dub pipeline on a local server 24/7 and trigger it remotely via Telegram. The user (1 person) sends a video link to the bot; the bot downloads, dubs, uploads to YouTube + Facebook Page (public), and reports per-step progress as edits to a single Telegram message. The translation step uses the existing `translate-video-segments` Claude Code skill invoked headlessly via the `claude` CLI, so the full pipeline runs autonomously with no human in the loop.

**In scope:** Long-polling Telegram bot, single-user whitelist, sequential job queue, Claude Code subprocess for translation, per-step progress reporting, crash isolation, both Windows (now) and Linux (later) service runner.

**Out of scope:** Multi-user, per-job parameter overrides, persistent queue, `/resume` from chat, file delivery via Telegram, voice cloning, real-time / live dub. See §10.

## 2. Constraints / Decisions chốt từ brainstorming

| Quyết định | Lý do |
|---|---|
| Translation mode: Hướng A (Claude Code subprocess) | User chốt; tận dụng skill đã có; tài khoản Claude trả phí có sẵn |
| Whitelist: 1 user duy nhất (`TELEGRAM_WHITELIST_USER_ID`) | YAGNI cho v1 personal use |
| Bot báo per-step status (which step done + success/failure + final URLs) | User chốt; edit-in-place single message |
| Đăng public ngay (không private/draft) | User chốt; override default của Task 5 trong auto-publish |
| Server: 24/7 | Windows dev → Linux later; design cross-platform |
| Queue: in-memory only, restart → mất pending jobs | User chốt; OK cho 1 user |
| Concurrency: 1 job/lúc (sequential) | LucyLab single-export, Demucs CPU, "phase 2+2 không parallel" |
| Error: fail-stop, KHÔNG auto-retry; user SSH resume thủ công | User chốt |

## 3. Architecture

### Process model
```
[Telegram] ←long-polling→ [python -m src.telegram_bot] (1 process, 24/7)
                            ├── bot.py        — handler registration, whitelist gate
                            ├── worker.py     — asyncio.Queue + 1 worker task
                            ├── progress.py   — ProgressReporter (edit-in-place)
                            ├── translator.py — Claude Code subprocess wrapper
                            └── config.py     — env loader

                          calls (in-process)
                            ▼
                          pipeline_vi.run_pipeline_vi(progress_callback=...)
                            ▼
                          subprocess: claude -p "translate skill..."
```

### File layout
```
src/telegram_bot/
├── __init__.py
├── bot.py            # main entry; CommandHandlers + MessageHandler; main() under __main__
├── worker.py         # Worker class: enqueue, run loop, _run_job, _report_crash
├── progress.py       # ProgressReporter class + DISPLAY_STEPS table + ICON map
├── translator.py     # translate_via_claude() async function + TranslateError + _wait_with_cancel
└── config.py         # load_config() → BotConfig dataclass
```

### Data flow per job
```
1. User sends URL → bot.on_message()
2. bot checks whitelist → enqueue(url) → worker.enqueue()
3. Worker reply "Job #N queued (position M)" via message.reply_text
4. Worker picks job → ProgressReporter(bot, job).start()
5. Worker calls asyncio.to_thread(run_pipeline_vi, url, ..., progress_callback=cb)
   - cb runs on pipeline thread; uses run_coroutine_threadsafe to dispatch
     reporter.update_step() back to bot's event loop
6. Pipeline returns {status: translate_pending, work_dir: ...}
7. Worker calls translate_via_claude(work_dir, cwd, cancel_event)
   - spawns `claude -p "<prompt>"`; waits for transcript_vi.json to appear
8. Worker calls run_pipeline_vi again with resume_dir + upload + public
9. Pipeline runs TTS → merge → upload, calling callback per step
10. Worker calls reporter.finalize(result) → message shows ✅ DONE + URLs
```

## 4. Bot Entry + Auth + Commands

### `src/telegram_bot/bot.py`

Library: `python-telegram-bot[ext]>=21.0` (async, long-polling).

```python
def main():
    cfg = load_config()
    app = Application.builder().token(cfg.bot_token).build()
    worker = Worker(bot=app.bot, claude_cwd=cfg.repo_root, work_dir_base=cfg.work_dir_base)

    app.bot_data["whitelist_user_id"] = cfg.whitelist_user_id
    app.bot_data["worker"] = worker

    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    asyncio.get_event_loop().create_task(worker.run())
    app.run_polling()
```

### Auth
Every handler's first line: `if update.effective_user.id != ctx.bot_data["whitelist_user_id"]: return`. Reject silently (no reply) so strangers don't discover the bot exists. Log a `logger.warning` with the offending user_id.

### Commands

| Command | Behavior |
|---|---|
| `/start`, `/help` | Welcome + command list |
| `/status` | Worker.status_summary(): "Current: Job #5 — TTS. Queue: 2 pending" or "Idle. Queue: 0 pending" |
| `/cancel` | Worker.cancel_current(): set cancel_event, edit current message |
| Plain text URL | on_message: enqueue if startswith http(s):// |

## 5. Job Queue + Worker

### `src/telegram_bot/worker.py`

```python
@dataclass
class Job:
    job_id: int
    url: str
    chat_id: int
    progress_message: Message
    work_dir: Path | None = None
    state: str = "queued"     # queued | running | done | failed | cancelled
    current_step: str = ""
    error: str | None = None
    enqueued_at: float = field(default_factory=time.time)


class Worker:
    def __init__(self, bot, claude_cwd, work_dir_base):
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.current: Job | None = None
        self._next_id = 1
        self._cancel_event = asyncio.Event()
        self._lock = asyncio.Lock()

    async def enqueue(self, url, chat_id, message) -> int: ...
    def status_summary(self) -> str: ...
    def cancel_current(self) -> str: ...
    async def run(self): ...                  # main loop, runs forever
    async def _run_job(self, job): ...        # phase1 → translate → phase2
    async def _report_crash(self, job, exc): ...
```

### Concurrency model
- `asyncio.Queue` for sequential FIFO, no Redis/Celery
- `asyncio.to_thread(run_pipeline_vi, ...)` wraps the sync pipeline call so the bot event loop stays responsive
- `progress_callback` fires on the pipeline thread → uses `asyncio.run_coroutine_threadsafe(reporter.update_step(...), loop)` to marshal back to the bot loop
- `_cancel_event` is checked between phase 1 ↔ translate ↔ phase 2 and inside the translator's `_wait_with_cancel`; we do NOT cancel mid-step (e.g., LucyLab call finishes whether you `/cancel` or not)

### Crash handling
Every job is wrapped in `try / except Exception`. On crash:
```
💥 Job #N FAILED at step `<step>`
Error: <type>: <msg>
Work dir: `<path>`
Resume: `python pipeline_vi.py --resume <path>`
```
Next queued job still runs.

### Default per-job params (v1 hard-coded)
`source_lang="zh"`, `voice_id="male"`, `bg_mode="duck"`, `bg_duck_db=-15.0`, `upload_platforms=["youtube", "facebook"]`, `public=True`.

## 6. Pipeline Integration + Claude Code Translator

### Pipeline refactor
Add **one** kwarg to `run_pipeline_vi()` (and symmetrically to `run_pipeline()`):

```python
def run_pipeline_vi(
    url, file_path, source_lang, voice_id, skip_video, output_dir,
    resume_dir=None, bg_mode="demucs", bg_duck_db=-12.0,
    upload_platforms=None, public=False,
    progress_callback=None,    # NEW: Callable[[step: str, status: str, **info], None]
) -> dict:
```

Helper inside pipeline:
```python
def _notify(step, status, **info):
    if progress_callback:
        try:
            progress_callback(step, status, **info)
        except Exception:
            logger.exception("progress_callback raised, ignoring")
```

Call `_notify(step, "running")` before each step and `_notify(step, "ok", **info)` after.

### Step names + info kwargs

| Step name | Trigger | Info kwargs on ok |
|---|---|---|
| `download` | Step 1 | `video_path` |
| `extract_audio` | Step 2 | — |
| `vocal_sep` | Step 2.5 (only when bg_mode=demucs) | — |
| `asr` | Step 3 | `n_segments` |
| `translate_pending` | written when pipeline exits at Step 4 | `work_dir` |
| `tts` | Step 5 (Steps 6a/6b/6c are not reported individually) | `n_segments`, `n_failed` |
| `merge_audio` | Step 6c | — |
| `merge_video` | Step 7 | `video_path` |
| `metadata` | Step 8 | — |
| `upload:youtube`, `upload:facebook` | Step 9 per platform | `url` on ok, `error` on fail |

Backward compat: `progress_callback=None` default → CLI mode unchanged, 44 existing tests pass.

**Note on the `translate` UI step:** The pipeline does NOT translate (it exits at Step 4 with `translate_pending` callback). The Worker emits `reporter.update_step("translate", "running" / "ok")` manually around its `translate_via_claude(...)` call. The reporter handles `translate_pending` step gracefully by ignoring it (it is not in `DISPLAY_STEPS`), preventing UI noise from the internal exit signal.

### `src/telegram_bot/translator.py`

```python
class TranslateError(RuntimeError): ...

async def translate_via_claude(
    work_dir: Path, cwd: Path, cancel_event: asyncio.Event, timeout_sec: int = 600,
) -> None:
    """Run `claude -p "<prompt>" --output-format text` in cwd.

    Skips if transcript_vi.json already exists.
    Raises TranslateError on non-zero exit, timeout, or missing output file.
    Raises asyncio.CancelledError on cancel_event.set().
    """
```

Prompt:
> Use the translate-video-segments skill to translate the transcript at `<work_dir>` from Chinese to Vietnamese. Read transcript_original.json, write transcript_vi.json with a text_vi field added to each segment. Do not run any other commands or ask follow-up questions.

Helper `_wait_with_cancel(proc, cancel_event)` races `proc.communicate()` vs `cancel_event.wait()`. On cancel: `proc.terminate()` → wait 5s → `proc.kill()` → raise CancelledError.

### Assumptions
- `claude` CLI in PATH on the bot server
- User logged in to Claude Pro/Max on that user account
- `.claude/skills/translate-video-segments/` exists in repo root (cwd of subprocess)
- Default timeout 600s covers 100+ segment videos

## 7. Telegram Message Format

### `src/telegram_bot/progress.py`

```python
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
ICON = {"running": "⏳", "ok": "✓", "fail": "✗", "pending": "·"}


class ProgressReporter:
    async def start(self): ...
    async def update_step(self, step, status, **info): ...
    async def finalize(self, result): ...
    def _render(self, header=None) -> str: ...
    def _collect_upload_urls(self, result) -> dict[str, str]: ...
    async def _edit(self, text): ...
```

### Rate limiting
Telegram allows 30 edits/sec/bot. ProgressReporter throttles to ≥1 second between `running` edits per job; `ok`/`fail` always edit immediately. `RetryAfter` exception caught → sleep + retry. `TimedOut` → drop edit, next one retries.

### Example outputs

**Starting:** all rows show `·`.
**Mid-flight:** completed rows show `✓`, current row shows `⏳`, future rows show `·`.
**Done:** `✅ Job #N DONE` header + all `✓` + URL footer `🔗 youtube: <url>` `🔗 facebook: <url>`.
**Failed:** `💥 Job #N FAILED at step <step>` + error + work dir + resume command.

### `_collect_upload_urls()`
Walks `self.step_info`, looks for `upload:*` keys with `url` field, returns `{platform: url}` dict for the footer.

## 8. Config + Service Runner

### `src/telegram_bot/config.py`

```python
@dataclass
class BotConfig:
    bot_token: str
    whitelist_user_id: int
    repo_root: Path           # cwd for claude subprocess
    work_dir_base: Path       # default output/VN/

def load_config() -> BotConfig:
    load_dotenv()
    bot_token = _required("TELEGRAM_BOT_TOKEN")
    whitelist_user_id = int(_required("TELEGRAM_WHITELIST_USER_ID"))
    repo_root = Path(os.environ.get("TELEGRAM_BOT_REPO_ROOT") or Path.cwd()).resolve()
    work_dir_base = Path(os.environ.get("TELEGRAM_BOT_WORK_DIR_BASE", "output/VN")).resolve()
    work_dir_base.mkdir(parents=True, exist_ok=True)
    return BotConfig(...)
```

### `.env.example` additions

```ini
# Telegram bot (only needed if you run `python -m src.telegram_bot`)
# 1) Create a bot via @BotFather on Telegram, copy the token
# 2) Find your own user_id by messaging @userinfobot on Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WHITELIST_USER_ID=
# Optional overrides:
# TELEGRAM_BOT_REPO_ROOT=/abs/path/to/Auto-Translade-video
# TELEGRAM_BOT_WORK_DIR_BASE=/abs/path/to/output/VN
```

### `requirements.txt` additions

```
python-telegram-bot[ext]>=21.0
```

### Service runner — Windows (now)

Recommend **NSSM** (free, auto-restart on crash):
```
nssm install AutoTranslateBot
  Path:               C:\Path\To\Python\python.exe
  Arguments:          -m src.telegram_bot
  Startup directory:  C:\...\Auto-Translade-video
  I/O:                stdout/stderr → C:\Logs\bot.log
  Exit actions:       Restart (5s delay)
nssm start AutoTranslateBot
```

Alternative: Task Scheduler `-AtLogOn` (built-in but no auto-restart).

### Service runner — Linux (later)

`deploy/auto-translate-bot.service` committed in v1 (harmless on Windows):
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

## 9. Testing Strategy

### Unit tests (no real Telegram / Claude / network)

```
tests/
├── test_telegram_bot_config.py
├── test_telegram_bot_progress.py
├── test_telegram_bot_worker.py
├── test_telegram_bot_translator.py
└── test_pipeline_callback.py
```

**config tests:** required env vars exit 1, whitelist must be int, work_dir auto-created, repo_root defaults to cwd.

**progress tests:** initial render all pending, step transitions update icons, ASR shows segment count, TTS shows failed count, upload URLs collected into footer, finalize fills unset steps.

**worker tests:** enqueue increments id, sequential execution, crash handling, cancel flow, translate_pending triggers Claude subprocess, progress_callback marshals threads correctly.

**translator tests:** skip when transcript exists, success path, subprocess failure, missing output file, timeout kills proc, cancel terminates proc.

**pipeline callback regression:** `progress_callback=None` works, callback exceptions don't fail pipeline, callback called for each step.

### Integration tests (opt-in)
`tests/integration/test_telegram_bot_real.py` — requires bot token + user_id + Claude CLI + Azure + LucyLab. Send a 10s test video, assert DONE within 5 min, cleanup uploaded videos. Not in CI.

### Existing tests
44 tests must still pass. Pipeline refactor only adds an optional kwarg with default None.

### Coverage target
~20 new unit tests, ~95% coverage of `src/telegram_bot/`.

## 10. Out of Scope / Future Work

### Future v2 (after v1 stable)
- Per-job params via caption (`/dub male zh demucs <link>`)
- Multi-user whitelist (`TELEGRAM_WHITELIST_USER_IDS=1,2,3`)
- Per-user queue isolation
- `/resume <work_dir>` command for retry without SSH
- Persistent queue (JSON or SQLite) — survive restart
- Send `dubbed_video.mp4` back via Telegram for preview
- `/history` showing last 10 jobs
- Webhook mode (when VPS with domain available)
- Multiple bot instances for parallel processing (needs multiple LucyLab accounts)
- HTTP `/health` endpoint for monitoring
- Inline keyboard for `/cancel`
- Auto-retry transient errors (network blip, LucyLab stuck)

### Explicit non-goals
- Voice cloning from user uploads
- Live / real-time dub
- Telegram bot as payment gateway / subscription tier
- Bot auto-generating content / scripts (Gemini only for metadata)
- Discord / Slack bot variants
- Parallel job execution within a single instance

## 11. Open Questions
None. All decisions chốt qua brainstorming.

## 12. Implementation Order

Suggested build sequence:
1. `src/telegram_bot/config.py` + .env.example + requirements.txt + tests
2. `src/telegram_bot/progress.py` + tests (pure rendering, no I/O)
3. `src/telegram_bot/translator.py` + tests (mocked subprocess)
4. Pipeline refactor — add `progress_callback` kwarg to both pipelines + regression tests
5. `src/telegram_bot/worker.py` + tests (mocked pipeline + reporter)
6. `src/telegram_bot/bot.py` + `__init__.py` + manual smoke test (real Telegram, fake URL)
7. End-to-end manual test with a real 10s test video
8. Deploy via NSSM + README documentation
9. Commit + push
