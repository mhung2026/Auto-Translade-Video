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
        [{"id": s["id"], "text": s["text"]} for s in segments],
        ensure_ascii=False,
        indent=2,
    )

    context_section = ""
    if context_segments:
        context_json = json.dumps(
            [{"id": s["id"], "text": s["text"]} for s in context_segments],
            ensure_ascii=False,
            indent=2,
        )
        context_section = f"""
PREVIOUS CONTEXT (for reference only, do NOT translate these):
{context_json}

"""

    return f"""You are a professional translator from {lang_name} to Japanese.
Below is a transcript from a video, split into segments.

REQUIREMENTS:
- Translate each segment into natural, concise Japanese
- Keep translations roughly similar in length to the original (they will be spoken aloud)
- Preserve technical terms accurately
- Return ONLY a JSON array with format: [{{"id": 1, "text_jp": "..."}}]
- Do not include any explanation, markdown, or extra text — only the JSON array
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
