"""Content generation via Claude Code subprocess.

Replaces the Gemini API path in src/content_generator.py for users who
prefer subscription-only AI usage (Claude Pro/Max + Higgsfield credits)
over per-request paid APIs.

- Metadata (title / description / hashtags) — Claude writes youtube_metadata.json
- Thumbnail image — Claude calls Higgsfield MCP, downloads to thumbnail.jpg

CLI:
    python -m src.content_via_claude metadata <work_dir>
    python -m src.content_via_claude thumbnail <work_dir>
    python -m src.content_via_claude all <work_dir>

Requires:
    - `claude` CLI in PATH and logged into a paid plan
    - Higgsfield MCP configured for Claude (only needed for thumbnail step)
"""
import argparse
import logging
import shlex
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class ContentError(RuntimeError):
    pass


METADATA_PROMPT = (
    "TASK: Use the Write tool to create '{work_dir}/youtube_metadata.json'. "
    "INPUT: Read '{work_dir}/transcript_vi.json' which is a JSON array of "
    "segments with fields id, text, text_vi, start, end, duration. "
    "OUTPUT FORMAT: a JSON object with EXACTLY 3 fields: "
    "title (string, 60-100 Vietnamese chars, hook in first 5 words, no clickbait), "
    "description (string, 200-500 Vietnamese words, open with a 1-2 sentence hook, "
    "summarize key points, end with 'Đăng ký kênh để xem thêm video chất lượng nhé!', "
    "use real newline characters for paragraph breaks), "
    "hashtags (array of 5-10 Vietnamese hashtags starting with #, use underscore "
    "for multi-word like #bể_cá, no spaces inside tags, mix broad and specific). "
    "STRICT: Do NOT print the JSON to stdout. Do NOT call any skill or MCP tool. "
    "Do NOT ask follow-up questions. After the Write tool succeeds, reply with "
    "EXACTLY the single word DONE and nothing else."
)


THUMBNAIL_PROMPT = (
    "TASK: Design and download a YouTube thumbnail image to "
    "'{work_dir}/thumbnail.jpg'. "
    "CONTEXT: Read '{work_dir}/transcript_vi.json' (first 3 segments) and "
    "'{work_dir}/youtube_metadata.json' (title) to understand the topic. "
    "STEP 1: Write a vivid English image-generation prompt yourself describing a "
    "visual subject related to the video, 16:9 YouTube thumbnail composition, "
    "high contrast vibrant colors, 1-2 main subjects clearly visible, "
    "professional photo or illustration style. Do NOT request any text overlay "
    "in the image. "
    "STEP 2: Use the Higgsfield MCP tool generate_image with model "
    "'nano-banana-pro' (fallback 'gpt-image-2'), aspect ratio 16:9, highest "
    "quality, ONE image only. "
    "STEP 3: After the generation job completes, download the image and save it "
    "to '{work_dir}/thumbnail.jpg' (JPG format, at least 1280x720). "
    "STRICT: Do NOT save to any other path. Do NOT generate variants. Do NOT "
    "ask follow-up questions. After the file is saved, reply with EXACTLY the "
    "single word DONE. If Higgsfield is unavailable, reply with ERROR followed "
    "by a one-line reason."
)


def _run_claude(prompt: str, cwd: Path, timeout_sec: int) -> None:
    """Sync wrapper around `claude -p`. Raises ContentError on failure."""
    # --dangerously-skip-permissions: needed for headless mode so claude
    # auto-approves file writes / tool calls without waiting for confirmation.
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "text",
        "--dangerously-skip-permissions",
    ]
    logger.info(f"Spawning claude -p (cwd={cwd}, timeout={timeout_sec}s)")
    # On Windows, claude is installed as claude.cmd by npm; subprocess.run
    # via CreateProcess doesn't find .cmd extensions automatically. Route
    # through the shell so PATHEXT resolves the wrapper.
    use_shell = sys.platform == "win32"
    if use_shell:
        invocation = subprocess.list2cmdline(cmd)
    else:
        invocation = cmd
    try:
        result = subprocess.run(
            invocation,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            shell=use_shell,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ContentError(f"claude -p timed out after {timeout_sec}s")
    except FileNotFoundError:
        raise ContentError("claude CLI not found in PATH. Install Claude Code first.")

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "")[:500]
        raise ContentError(f"claude -p exited {result.returncode}: {err}")


def generate_metadata_via_claude(
    work_dir: str,
    target_lang: str = "vi-VN",
    timeout_sec: int = 300,
) -> Path:
    """Invoke Claude to read transcript_vi.json and write youtube_metadata.json.

    Skips if youtube_metadata.json already exists.
    Returns the path to the output file. Raises ContentError on failure.
    """
    work_dir_path = Path(work_dir).resolve()
    out = work_dir_path / "youtube_metadata.json"
    if out.exists() and out.stat().st_size > 0:
        logger.info(f"Metadata already exists, skipping Claude: {out}")
        return out

    transcript = work_dir_path / "transcript_vi.json"
    if not transcript.exists():
        raise ContentError(
            f"transcript_vi.json not found in {work_dir} — translate step must run first"
        )

    prompt = METADATA_PROMPT.format(work_dir=str(work_dir_path))
    # Run from repo root so Claude has access to project skills if needed.
    repo_root = _guess_repo_root(work_dir_path)
    _run_claude(prompt, cwd=repo_root, timeout_sec=timeout_sec)

    if not out.exists():
        raise ContentError(
            f"Claude finished but youtube_metadata.json not created at {out}"
        )
    logger.info(f"Metadata written: {out}")
    return out


def generate_thumbnail_via_claude(
    work_dir: str,
    timeout_sec: int = 900,
) -> Path:
    """Invoke Claude with Higgsfield MCP to generate thumbnail.jpg.

    Skips if thumbnail.jpg already exists.
    Returns the path to the output file. Raises ContentError on failure.
    """
    work_dir_path = Path(work_dir).resolve()
    out = work_dir_path / "thumbnail.jpg"
    if out.exists() and out.stat().st_size > 0:
        logger.info(f"Thumbnail already exists, skipping Claude: {out}")
        return out

    metadata = work_dir_path / "youtube_metadata.json"
    if not metadata.exists():
        raise ContentError(
            "youtube_metadata.json not found — run metadata step first"
        )

    prompt = THUMBNAIL_PROMPT.format(work_dir=str(work_dir_path))
    repo_root = _guess_repo_root(work_dir_path)
    _run_claude(prompt, cwd=repo_root, timeout_sec=timeout_sec)

    if not out.exists():
        raise ContentError(
            f"Claude finished but thumbnail.jpg not created at {out}"
        )
    logger.info(f"Thumbnail written: {out}")
    return out


def _guess_repo_root(work_dir_path: Path) -> Path:
    """Walk up from work_dir to find the repo root (has pipeline_vi.py).

    Fallback: current working directory.
    """
    for parent in [work_dir_path, *work_dir_path.parents]:
        if (parent / "pipeline_vi.py").exists():
            return parent
    return Path.cwd()


def main():
    parser = argparse.ArgumentParser(prog="python -m src.content_via_claude")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_meta = sub.add_parser("metadata", help="Generate youtube_metadata.json")
    p_meta.add_argument("work_dir")

    p_thumb = sub.add_parser("thumbnail", help="Generate thumbnail.jpg via Higgsfield")
    p_thumb.add_argument("work_dir")

    p_all = sub.add_parser("all", help="Generate metadata then thumbnail")
    p_all.add_argument("work_dir")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.cmd == "metadata":
            print(generate_metadata_via_claude(args.work_dir))
        elif args.cmd == "thumbnail":
            print(generate_thumbnail_via_claude(args.work_dir))
        elif args.cmd == "all":
            print(generate_metadata_via_claude(args.work_dir))
            print(generate_thumbnail_via_claude(args.work_dir))
    except ContentError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
