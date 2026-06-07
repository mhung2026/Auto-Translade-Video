"""Wrapper around the Claude Code CLI for headless translation.

Requires:
- `claude` CLI installed (https://claude.com/claude-code)
- User logged into a paid Claude plan (Pro/Max) on this machine
- Skill `translate-video-segments` available in this repo's .claude/skills/
"""
import asyncio
import logging
import subprocess
import sys
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

    # Inline instructions (do NOT invoke the translate-video-segments skill —
    # skills can hang in headless `-p` mode if they expect user confirmation).
    prompt = (
        f"Read the JSON file at {work_dir}\\transcript_original.json. "
        f"It is an array of segments with fields: id, text, start, end, duration. "
        f"Auto-detect the source language of `text` and translate each segment "
        f"to Vietnamese, adding the translation as a new `text_vi` field. "
        f"Write the result to {work_dir}\\transcript_vi.json with the same shape "
        f"(preserve every original field, append text_vi).\n\n"
        f"Vietnamese style rules:\n"
        f"- YouTube-creator tone: bạn / mình / các bạn (no mày/tao).\n"
        f"- Drop filler words and discourse particles (啊/呢/嘛/吧 etc.).\n"
        f"- Keep brand names original; use pinyin/romanization for character names.\n"
        f"- For bleeped segments (text contains only `**` or punctuation), use a "
        f"short exclamation like \"Hả.\" or \"Á.\" — never empty or just \"...\".\n"
        f"- Match each Vietnamese segment to the original duration "
        f"(~12 chars/sec Vietnamese is natural).\n\n"
        f"IMPORTANT: Do this work yourself directly — DO NOT invoke any skill, "
        f"DO NOT call any MCP tool, DO NOT ask any follow-up questions. "
        f"Just read the input file, write the output file, and stop."
    )
    cmd = ["claude", "-p", prompt, "--output-format", "text"]
    logger.info(f"Spawning Claude Code in cwd={cwd}")

    # On Windows the `claude` CLI installs as `claude.cmd` (npm wrapper),
    # which create_subprocess_exec can't execute (CreateProcess only finds .exe).
    # Go through the shell so PATHEXT finds the .cmd file.
    if sys.platform == "win32":
        proc = await asyncio.create_subprocess_shell(
            subprocess.list2cmdline(cmd),
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
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
