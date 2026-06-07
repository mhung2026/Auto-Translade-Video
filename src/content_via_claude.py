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


METADATA_PROMPT = """\
You are generating YouTube metadata for a Vietnamese-language dub video.

Read this file:
  {work_dir}/transcript_vi.json

It contains an array of segments with fields: id, text (original), text_vi (Vietnamese), start, end, duration.

Write this output file with EXACTLY the JSON shape shown below:
  {work_dir}/youtube_metadata.json

Schema:
{{
  "title": "<60-100 chars, Vietnamese, click-friendly, no clickbait lies>",
  "description": "<200-500 words Vietnamese, see rules below>",
  "hashtags": ["#tag1", "#tag2", "..."]
}}

TITLE RULES:
- 60-100 characters in Vietnamese
- Hook attention in first 5 words
- Click-friendly but honest (no clickbait lies)
- Avoid emojis unless they fit naturally
- Lowercase is fine, do not stuff keywords

DESCRIPTION RULES:
- 200-500 Vietnamese words
- Open with a 1-2 sentence hook that summarizes the video
- Middle: bullet-style or paragraph summary of key points from the transcript
- End with: "Đăng ký kênh để xem thêm video chất lượng nhé!"
- Use real newlines (\\n) for paragraph breaks; do NOT escape them as literal "\\n"

HASHTAGS RULES:
- 5 to 10 hashtags
- Mix of broad (e.g. #YouTube, #review) and specific (related to the actual topic)
- Vietnamese; use underscore for multi-word tags (e.g. #bể_cá, #lọc_nước)
- No spaces inside tags
- Each hashtag must start with #

OUTPUT:
- Write ONLY the JSON file at the path above.
- Do NOT print the JSON to stdout.
- Do NOT run any other commands or skills.
- Do NOT call any MCP tool.
- Do NOT ask follow-up questions.
- Do this work yourself directly. Stop as soon as the file is written.
- If transcript_vi.json is missing or malformed, exit with a clear error message.
"""


THUMBNAIL_PROMPT = """\
You are designing a YouTube thumbnail image for a Vietnamese-language dub video.

CONTEXT FILES TO READ in {work_dir}:
  - transcript_vi.json (read the first 3 segments to understand the topic)
  - youtube_metadata.json (read the title)

STEP 1: Design a vivid English image-generation prompt yourself based on the content.
   The prompt should describe:
   - A visual subject directly related to the video's topic
   - 16:9 aspect ratio YouTube thumbnail composition
   - High contrast, vibrant colors that pop on a mobile screen
   - 1-2 main subjects, clearly visible
   - Professional photo or illustration style (your choice based on topic)
   - DO NOT request any text in the image (no captions, no overlay text — keep it visual only)

STEP 2: Generate the image using the Higgsfield MCP tool.
   - First choice of model: "nano-banana-pro"
   - If that model is unavailable in your workspace, try: "gpt-image-2"
   - Aspect ratio: 16:9
   - Quality: the highest the model supports
   - Generate ONE image only (no variants)

STEP 3: After the generation job completes, download the image and save it to:
   {work_dir}/thumbnail.jpg

   - Format: JPG
   - Resolution: at least 1280x720
   - If the image is larger, that's fine — YouTube will accept up to 2 MB

CONSTRAINTS:
- DO NOT save to any other path
- DO NOT generate multiple images
- DO NOT run unrelated commands
- DO NOT ask follow-up questions
- If Higgsfield MCP is not available in this workspace, report the error clearly and exit
"""


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
