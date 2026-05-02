import json
import re
import anthropic
import config
from src.utils import setup_logging

logger = setup_logging("translator")

LANG_NAMES = {
    "en-US": "English",
    "en": "English",
    "vi-VN": "Vietnamese",
    "vi": "Vietnamese",
    "zh-CN": "Chinese (Mandarin, Simplified)",
    "zh-HK": "Chinese (Cantonese, Traditional)",
    "zh-TW": "Chinese (Mandarin, Traditional)",
    "zh": "Chinese",
}


def _split_into_batches(segments: list[dict], batch_size: int = 25) -> list[list[dict]]:
    if not segments:
        return []
    batches = []
    for i in range(0, len(segments), batch_size):
        batches.append(segments[i : i + batch_size])
    return batches


def _build_prompt(segments: list[dict], source_lang: str, context_segments: list[dict] | None = None) -> str:
    lang_name = LANG_NAMES.get(source_lang, source_lang)
    segments_json = json.dumps(
        [{"id": s["id"], "text": s["text"], "duration": round(s["duration"], 2)} for s in segments],
        ensure_ascii=False,
        indent=2,
    )

    context_section = ""
    if context_segments:
        context_json = json.dumps(
            [{"id": s["id"], "text": s["text"], "duration": round(s["duration"], 2)} for s in context_segments],
            ensure_ascii=False,
            indent=2,
        )
        context_section = f"""
PREVIOUS CONTEXT (for reference only, do NOT translate these):
{context_json}

"""

    is_chinese = source_lang.startswith("zh")
    chinese_note = """
CHINESE → JAPANESE SPECIFICS:
- Many 漢字 are shared between Chinese and Japanese — leverage them when natural,
  but use the JAPANESE reading/meaning, not Chinese pronunciation.
- Beware of false friends: 手紙 (letter in JP, toilet paper in ZH), 勉強 (study in JP, force in ZH).
  Always pick the JAPANESE meaning that fits the context.
- Chinese is more compact per character — Japanese translation is often LONGER.
  Be aggressive about choosing short Japanese expressions to fit the duration.
- For Cantonese (zh-HK) sources, treat ASR text as written Mandarin equivalent.
""" if is_chinese else ""

    return f"""You are a translator for YouTube videos about sports, fitness, and entertainment.
Translate {lang_name} to Japanese. This is casual content — NOT formal business or academic.

STYLE RULES:
- Use casual/plain form (だ/である体), NOT polite form (です/ます体)
- Keep it short and punchy — match the energy of the original
- Use タメ口 (casual speech) like a fitness YouTuber would speak
- Omit unnecessary particles and filler — be direct
{chinese_note}
DURATION-AWARE TRANSLATION (CRITICAL):
- Each segment has a "duration" field in seconds — this is the time window the Japanese audio must fit into.
- You MUST analyze the duration and choose Japanese expressions that can be spoken within that time.
- Japanese speech is approximately 7-8 characters per second at normal speed (max 10 chars/sec at 130% speed).
- For SHORT segments (< 4s): Use the shortest possible expression. Use 省略形, contractions, drop particles aggressively.
- For MEDIUM segments (4-8s): Use natural casual Japanese. Prefer shorter synonyms when multiple options exist.
- For LONG segments (> 8s): You have more room, but still avoid unnecessarily verbose expressions.
- Example: "You can have big biceps" (2s) → "太い二頭筋あっても" (short) NOT "大きな上腕二頭筋を持っていても" (too long)
- When in doubt, choose the SHORTER form. It's easier to slow down TTS than to speed it up beyond 130%.

REQUIREMENTS:
- Return ONLY a JSON array: [{{"id": 1, "text_jp": "..."}}]
- No explanation, no markdown, no extra text
{context_section}
SEGMENTS TO TRANSLATE:
{segments_json}"""


def translate_segments(segments: list[dict], source_lang: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    batches = _split_into_batches(segments, batch_size=25)

    logger.info(
        f"Translating {len(segments)} segments in {len(batches)} batch(es) "
        f"using model {config.ANTHROPIC_MODEL}"
    )

    translations = {}

    for batch_idx, batch in enumerate(batches):
        # Include 2-3 segments from previous batch as context (for batches after the first)
        context_segments = []
        if batch_idx > 0 and len(batches) > 1:
            prev_batch = batches[batch_idx - 1]
            context_segments = prev_batch[-3:]  # Last 3 segments of previous batch

        logger.info(
            f"Processing batch {batch_idx + 1}/{len(batches)} "
            f"({len(batch)} segments, {len(context_segments)} context)"
        )

        prompt = _build_prompt(batch, source_lang, context_segments=context_segments)

        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()

        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r'```(?:json)?\s*\n(.*?)```', response_text, re.DOTALL)
        if fence_match:
            response_text = fence_match.group(1).strip()

        try:
            translated = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response for batch {batch_idx + 1}: {e}")
            logger.error(f"Raw response: {response_text[:500]}")
            continue

        for item in translated:
            if isinstance(item, dict) and "id" in item and "text_jp" in item:
                translations[item["id"]] = item["text_jp"]
            else:
                logger.warning(f"Skipping malformed translation item: {item}")

    for seg in segments:
        if seg["id"] in translations:
            seg["text_jp"] = translations[seg["id"]]
        else:
            logger.warning(f"Missing translation for segment {seg['id']}")
            seg["text_jp"] = seg["text"]

    logger.info(f"Translation complete: {len(translations)}/{len(segments)} segments translated")
    return segments
