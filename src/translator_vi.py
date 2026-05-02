"""Translator module: EN → Vietnamese using Claude API.

Translates segments with duration-aware prompting for video dubbing.
"""
import json
import re
import anthropic
import config
from src.utils import setup_logging

logger = setup_logging("translator_vi")

LANG_NAMES = {
    "en-US": "English",
    "en": "English",
    "ja-JP": "Japanese",
    "ja": "Japanese",
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
CHINESE → VIETNAMESE SPECIFICS:
- Use Sino-Vietnamese (Hán-Việt) words ONLY when they are everyday Vietnamese
  (e.g. "tài phiệt", "kiểm sát viên", "phim truyền hình") — avoid academic-sounding
  ones ("nhật báo", "tự sát" → prefer "báo chí", "tự tử" in casual review tone).
- Korean drama / pop names: keep the Korean Romanization the Vietnamese audience
  knows (朱志勋 → Joo Ji-hoon, 河智苑 → Ha Ji-won), NOT pinyin and NOT Vietnamese
  phonetic spelling. If you can't tell, transliterate the pinyin (e.g. 方太谢
  → Fang Tai-xie). Keep brand names in original (Mercedes, not "xe Mẹc").
- For Cantonese (zh-HK) sources, treat ASR text as Mandarin equivalent for translation.
- Drop Chinese discourse particles (啊/呢/嘛/吧) — Vietnamese has different filler
  patterns; use "nha", "đó", "ấy" only when adding genuine warmth.
- Beware of false friends: 工作 = công việc (NOT công tác), 检察官 = kiểm sát viên
  (NOT công tố — though công tố is OK in news context), 老婆 = vợ (casual, NOT phu nhân).
""" if is_chinese else ""

    return f"""You are a translator for YouTube videos about sports, fitness, and entertainment.
Translate {lang_name} to Vietnamese. This is casual content — NOT formal business or academic.

STYLE RULES:
- Use friendly, conversational Vietnamese — like a YouTuber talking to their audience
- ALWAYS use "bạn/mình/các bạn" tone — friendly and approachable. NEVER use "mày/tao" or "ông/bà"
- Keep it natural and engaging — avoid stiff, textbook Vietnamese
- Use common, easy-to-understand words (e.g., "bắp tay" not "cơ nhị đầu cánh tay")
- Be direct, skip unnecessary filler words
- Speak as if narrating/presenting to viewers, not talking to a friend privately
{chinese_note}
DURATION-AWARE TRANSLATION (CRITICAL):
- Each segment has a "duration" field in seconds — this is the time window the Vietnamese audio must fit into.
- You MUST analyze the duration and choose Vietnamese expressions that can be spoken within that time.
- Vietnamese speech is approximately 4-5 words per second at normal speed (max ~6 words/sec at 130% speed).
- For SHORT segments (< 4s): Use the shortest possible expression. Drop unnecessary words aggressively.
- For MEDIUM segments (4-8s): Use natural casual Vietnamese. Prefer shorter synonyms when options exist.
- For LONG segments (> 8s): You have more room, but still avoid unnecessarily verbose expressions.
- When in doubt, choose the SHORTER form. It's easier to slow down TTS than to speed it up beyond 130%.

REQUIREMENTS:
- Return ONLY a JSON array: [{{"id": 1, "text_vi": "..."}}]
- No explanation, no markdown, no extra text
{context_section}
SEGMENTS TO TRANSLATE:
{segments_json}"""


def translate_segments_vi(segments: list[dict], source_lang: str) -> list[dict]:
    """Translate segments to Vietnamese using Claude API.

    Args:
        segments: List of dicts with id, text, start, end, duration
        source_lang: Source language code (e.g., "en-US")

    Returns:
        Same segments list with text_vi field added
    """
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    batches = _split_into_batches(segments, batch_size=25)

    logger.info(
        f"Translating {len(segments)} segments in {len(batches)} batch(es) "
        f"using model {config.ANTHROPIC_MODEL}"
    )

    translations = {}

    for batch_idx, batch in enumerate(batches):
        context_segments = []
        if batch_idx > 0 and len(batches) > 1:
            prev_batch = batches[batch_idx - 1]
            context_segments = prev_batch[-3:]

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

        # Strip markdown code fences
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
            if isinstance(item, dict) and "id" in item and "text_vi" in item:
                translations[item["id"]] = item["text_vi"]
            else:
                logger.warning(f"Skipping malformed translation item: {item}")

    for seg in segments:
        if seg["id"] in translations:
            seg["text_vi"] = translations[seg["id"]]
        else:
            logger.warning(f"Missing translation for segment {seg['id']}")
            seg["text_vi"] = seg["text"]

    logger.info(f"Translation complete: {len(translations)}/{len(segments)} segments translated")
    return segments
