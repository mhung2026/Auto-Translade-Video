import json
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


def _build_prompt(segments: list[dict], source_lang: str) -> str:
    lang_name = LANG_NAMES.get(source_lang, source_lang)
    segments_json = json.dumps(
        [{"id": s["id"], "text": s["text"]} for s in segments],
        ensure_ascii=False,
        indent=2,
    )
    return f"""You are a professional translator from {lang_name} to Japanese.
Below is a transcript from a video, split into segments.

REQUIREMENTS:
- Translate each segment into natural, concise Japanese
- Keep translations roughly similar in length to the original (they will be spoken aloud)
- Preserve technical terms accurately
- Return ONLY a JSON array with format: [{{"id": 1, "text_jp": "..."}}]
- Do not include any explanation, markdown, or extra text — only the JSON array

SEGMENTS:
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
        logger.info(f"Processing batch {batch_idx + 1}/{len(batches)} ({len(batch)} segments)")

        prompt = _build_prompt(batch, source_lang)

        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3].strip()

        translated = json.loads(response_text)

        for item in translated:
            translations[item["id"]] = item["text_jp"]

    for seg in segments:
        if seg["id"] in translations:
            seg["text_jp"] = translations[seg["id"]]
        else:
            logger.warning(f"Missing translation for segment {seg['id']}")
            seg["text_jp"] = seg["text"]

    logger.info(f"Translation complete: {len(translations)}/{len(segments)} segments translated")
    return segments
