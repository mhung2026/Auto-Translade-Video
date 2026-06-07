"""Write TRANSLATE_PENDING.txt with instructions for both Claude Code users
and casual users (no API key, no CLI tools — use ChatGPT / Gemini web UI).

The pipeline writes this file when the translation step is reached and the
expected translated transcript JSON does not yet exist on disk. The file is
a self-contained set of instructions: the user picks Path A (Claude Code) or
Path B (web AI), produces the translated JSON, and runs ``--resume`` to
continue.
"""
import os


def write_hint(work_dir: str, target_lang: str, source_lang: str) -> str:
    """Create ``<work_dir>/TRANSLATE_PENDING.txt`` and return its path."""
    is_vi = target_lang == "vi-VN"
    target_name = "Vietnamese" if is_vi else "Japanese"
    out_field = "text_vi" if is_vi else "text_jp"
    out_file = "transcript_vi.json" if is_vi else "transcript_jp.json"
    resume_script = "pipeline_vi.py" if is_vi else "pipeline.py"
    pace = ("Vietnamese: ~12 chars/sec normal, ~15 chars/sec max at 1.3x"
            if is_vi
            else "Japanese: ~7-8 chars/sec normal, ~10 chars/sec max at 1.3x")

    if is_vi:
        style_rules = """- Bạn / mình / các bạn (never mày/tao, never ông/bà).
- Casual YouTube-creator tone, direct, skip filler.
- Chinese-origin character names → pinyin (e.g. 方太谢 → Fang Tai-xie).
- Korean drama names → Korean Romanization the VN audience knows
  (e.g. 朱志勋 → Joo Ji-hoon, 河智苑 → Ha Ji-won).
- Brand names stay original (Mercedes, Samsung). Sino-Vietnamese only when
  everyday ("kiểm sát viên" OK, but "tự tử" not "tự sát" in casual tone).
- Drop Chinese discourse particles (啊/呢/嘛/吧).
- Bleeped/censored segments (text contains only "**" or punctuation): use a
  short Vietnamese exclamation like "Hả." or "Á." — DO NOT output "..." or
  empty string (the TTS service rejects pure-punctuation text)."""
    else:
        style_rules = """- Casual plain form (だ/である体), NOT polite (です/ます体).
- タメ口, short and punchy, drop unnecessary particles.
- For Chinese sources: use Japanese readings/meanings of shared 漢字, not
  Chinese. Watch false friends (手紙 JP=letter / ZH=toilet paper).
- Bleeped segments (text contains only "**"): use a short exclamation
  like "あー" or "うっ" — DO NOT output "..." or empty string."""

    hint_path = os.path.join(work_dir, "TRANSLATE_PENDING.txt")
    with open(hint_path, "w", encoding="utf-8") as f:
        f.write(
            f"""TRANSLATION STEP PENDING
========================

Source language : {source_lang}
Target language : {target_lang} ({target_name})
Work directory  : {work_dir}

The pipeline stopped at Step 4 because {out_file} does not exist yet.
Pick ONE of the two paths below to create that file, then resume.


==============================================================
PATH A — Claude Code users (or anyone with Claude subscription)
==============================================================

In Claude Code, say:

    Translate the transcript at {work_dir} to {target_name}.

(or run the skill directly: /translate-video-segments)

The translate-video-segments skill reads transcript_original.json, applies
the same style rules shown below, and writes {out_file} with one "{out_field}"
field added per segment.


==============================================================
PATH B — No API key, no Claude Code (ChatGPT / Gemini web UI)
==============================================================

1. Open transcript_original.json in this folder.
2. Open ChatGPT or Gemini (web). Start a fresh chat.
3. Paste the PROMPT BELOW, then paste the entire contents of
   transcript_original.json directly after it, and send.
4. The AI returns a JSON array. Copy it.
5. Save the copy as {out_file} in this folder (same directory as
   transcript_original.json). Make sure encoding is UTF-8.
6. Resume:

    python {resume_script} --resume "{work_dir}" --file <original_video.mp4>

----- PROMPT TO COPY -----
You are translating an ASR transcript for a YouTube dub from {source_lang}
to {target_name}. Below is a JSON array of segments. Each has: id, text,
start, end, duration (seconds).

OUTPUT FORMAT (STRICT):
- Return ONE JSON array, same length, same order, same ids.
- Preserve every original field: id, text, start, end, duration.
- ADD one new string field per segment: "{out_field}"
- "{out_field}" must be the {target_name} translation of "text".
- Output valid JSON only — no markdown fences, no commentary.

STYLE:
{style_rules}

DURATION-AWARE LENGTH (CRITICAL):
- Each segment carries duration (seconds). The TTS that runs after this
  step must fit in that window. Spoken pace: {pace}.
- Short (<4s): use the shortest natural phrasing, drop particles.
- Medium (4-8s): natural casual speech, prefer shorter synonyms.
- Long (>8s): more room, but still tight — avoid bloat.
- When in doubt, choose the SHORTER form.

CONSISTENCY:
- Use the same translation for recurring character names, recurring terms,
  and register/pronouns across the whole transcript.

Now translate this JSON, return only the translated JSON array:

(paste transcript_original.json contents here)
----- END PROMPT -----

If the AI replies with the JSON wrapped in ```json ... ``` fences, strip
the fences before saving. Verify the saved file with:

    python -c "import json; d=json.load(open(r'{work_dir}/{out_file}', encoding='utf-8')); print('segments:', len(d)); print('first {out_field}:', d[0].get('{out_field}'))"

The pipeline will detect {out_file} on resume, skip Step 4, and continue
with TTS, audio fitting, video merge, and metadata generation.
"""
        )
    return hint_path
