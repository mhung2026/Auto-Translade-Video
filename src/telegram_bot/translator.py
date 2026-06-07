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

    # IMPORTANT: must be a single line (no \n) because the prompt is passed
    # as a Windows command-line argument and CMD truncates multi-line args.
    input_path = (work_dir / "transcript_original.json").as_posix()
    output_path = (work_dir / "transcript_vi.json").as_posix()
    prompt = (
        f"TASK: Use the Write tool to create '{output_path}'. "
        f"INPUT: Read '{input_path}' which is a JSON array of segments "
        f"(fields: id, text, start, end, duration). "
        f"OUTPUT: A JSON array with the same length and order; for every segment "
        f"preserve every original field exactly AND append a new string field "
        f"'text_vi' containing the Vietnamese translation of 'text'. "
        f"RULES: Auto-detect source language. Translate to Vietnamese with a "
        f"YouTube-creator tone (use 'bạn'/'mình'/'các bạn', never 'mày'/'tao'). "
        f"Drop filler particles. Keep brand names original; pinyin/romanization "
        f"for Asian character names. For bleeped segments (text is only '**' or "
        f"punctuation) use a short exclamation like 'Hả.' or 'Á.' — never empty "
        f"or just '...'. Aim for about 12 Vietnamese characters per second of "
        f"segment duration. "
        f"STRICT: Do NOT display the JSON in your reply. Do NOT print a markdown "
        f"table preview. Do NOT invoke any skill or MCP tool. After the Write "
        f"tool succeeds, reply with EXACTLY the single word DONE and nothing "
        f"else. If you cannot complete the task, reply with ERROR followed by a "
        f"one-line reason."
    )
    # --dangerously-skip-permissions: auto-approve every tool call so the
    # subprocess never blocks waiting for a permission prompt that no human
    # can answer in headless mode.
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "text",
        "--dangerously-skip-permissions",
    ]
    logger.info(f"Spawning Claude Code in cwd={cwd}")

    # On Windows the `claude` CLI installs as `claude.cmd` (npm wrapper),
    # which create_subprocess_exec can't execute (CreateProcess only finds .exe).
    # Go through the shell so PATHEXT finds the .cmd file.
    # stdin=DEVNULL: prevent claude from blocking on stdin in headless mode.
    if sys.platform == "win32":
        proc = await asyncio.create_subprocess_shell(
            subprocess.list2cmdline(cmd),
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
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
