"""Content Generator — Thumbnails + YouTube metadata using Google Gemini API.

Generates:
- 2 thumbnail images (with text overlay in target language)
- YouTube metadata (title, description, hashtags)
- Clean script text files (extracted from transcript JSON)
"""
import json
import os
import re
import time

import requests
from google import genai
from google.genai import types

from src.utils import setup_logging

logger = setup_logging("content_generator")


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    if not url:
        return None
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_original_thumbnail(url: str, output_dir: str) -> str | None:
    """Download original video thumbnail from YouTube."""
    video_id = _extract_video_id(url)
    if not video_id:
        logger.warning("Could not extract video ID from URL, skipping thumbnail fetch")
        return None

    thumb_urls = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    ]

    for thumb_url in thumb_urls:
        try:
            resp = requests.get(thumb_url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1000:
                path = os.path.join(output_dir, "thumbnail_original.jpg")
                with open(path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Original thumbnail downloaded: {path}")
                return path
        except requests.RequestException:
            continue

    logger.warning("Could not download original thumbnail")
    return None


def extract_script_text(segments: list[dict], text_field: str, output_path: str) -> str:
    """Extract plain text from transcript segments and save to .txt file.

    Returns the plain text string.
    """
    lines = []
    for seg in segments:
        text = seg.get(text_field, seg.get("text", "")).strip()
        if text:
            lines.append(text)

    script_text = " ".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script_text)

    logger.info(f"Script extracted: {output_path} ({len(script_text)} chars)")
    return script_text


def generate_youtube_metadata(
    script_original: str,
    script_translated: str,
    target_lang: str,
    source_url: str,
    api_key: str,
    model_id: str,
) -> dict:
    """Generate YouTube title, description, hashtags using Gemini text model.

    Takes plain text scripts (not segments JSON).
    Returns dict with keys: title, description, hashtags
    """
    if target_lang == "vi-VN":
        lang_name = "Vietnamese"
        lang_instruction = (
            "Write ALL output in Vietnamese. "
            "Use friendly, engaging Vietnamese suitable for YouTube."
        )
    else:
        lang_name = "Japanese"
        lang_instruction = (
            "Write ALL output in Japanese. "
            "Use natural, engaging Japanese suitable for YouTube."
        )

    # Trim scripts to keep prompt small
    orig_trimmed = script_original[:800]
    trans_trimmed = script_translated[:1200]

    prompt = f"""You are a YouTube content strategist. Based on the video script below, generate:

1. **Title**: Catchy, SEO-optimized YouTube title (max 80 chars). Must be in {lang_name}.
2. **Description**: Detailed video description (200-400 words) in {lang_name}. Include:
   - Brief intro (what the video is about)
   - Key points covered
   - Call to action (subscribe, like, comment)
3. **Hashtags**: 15-20 relevant hashtags. Mix of {lang_name} and English hashtags.

{lang_instruction}

Original script:
{orig_trimmed}

Translated script ({lang_name}):
{trans_trimmed}

Respond in this exact JSON format (no markdown code blocks):
{{"title": "...", "description": "...", "hashtags": ["#tag1", "#tag2", ...]}}"""

    client = genai.Client(api_key=api_key)

    # Retry with exponential backoff for 503/transient errors
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=4000,
                ),
            )
            break
        except Exception as e:
            error_str = str(e)
            is_transient = "503" in error_str or "UNAVAILABLE" in error_str or "ServerError" in type(e).__name__
            if is_transient and attempt < max_retries - 1:
                wait = (attempt + 1) * 15  # 15s, 30s, 45s, 60s
                logger.warning(f"Metadata API error, retrying in {wait}s (attempt {attempt + 1}/{max_retries}): {error_str[:80]}")
                time.sleep(wait)
            else:
                raise

    text = response.text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        metadata = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"JSON parse failed, attempting repair: {text[:100]}...")
        repaired = False
        # Try progressively more aggressive closing sequences
        suffixes = ['"}', ']}', '"]}', '""]}', '" ]}', '"}', '"]  }', '"] }']
        for suffix in suffixes:
            try:
                metadata = json.loads(text + suffix)
                logger.info(f"JSON repaired with suffix: {suffix}")
                repaired = True
                break
            except json.JSONDecodeError:
                continue

        if not repaired:
            # Extract fields manually with regex
            title_match = re.search(r'"title"\s*:\s*"([^"]*)"', text)
            desc_match = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            tags = re.findall(r'"(#[^"]+)"', text)
            if title_match:
                metadata = {
                    "title": title_match.group(1),
                    "description": desc_match.group(1) if desc_match else "",
                    "hashtags": tags,
                }
                logger.info("JSON extracted via regex fallback")
            else:
                logger.error(f"Failed to parse/repair metadata JSON: {text[:200]}")
                metadata = {
                    "title": "Video",
                    "description": text,
                    "hashtags": [],
                }

    logger.info(f"YouTube metadata generated: title='{metadata.get('title', '')[:50]}...'")
    return metadata


def generate_thumbnails(
    script_original: str,
    script_translated: str,
    target_lang: str,
    original_thumbnail_path: str | None,
    output_dir: str,
    api_key: str,
    model_id: str,
) -> list[str]:
    """Generate 2 thumbnail images using Gemini image model.

    Takes plain text scripts (not segments JSON).
    Returns list of saved thumbnail file paths.
    """
    if target_lang == "vi-VN":
        lang_name = "tiếng Việt"
        lang_code = "Vietnamese"
    else:
        lang_name = "日本語"
        lang_code = "Japanese"

    # Only need a short summary for thumbnail prompt
    orig_short = script_original[:400]
    trans_short = script_translated[:400]

    client = genai.Client(api_key=api_key)
    saved_paths = []

    # Load original thumbnail as reference if available
    ref_image_part = None
    if original_thumbnail_path and os.path.exists(original_thumbnail_path):
        with open(original_thumbnail_path, "rb") as f:
            image_bytes = f.read()
        ref_image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg",
        )
        logger.info("Using original thumbnail as reference for generation")

    thumbnail_prompts = [
        f"""Create a professional YouTube thumbnail image (16:9 aspect ratio, 1280x720).

The video is about:
{orig_short}

Requirements:
- Bold, eye-catching design with vibrant colors
- Include SHORT {lang_code} text overlay (max 5-6 words) that summarizes the video topic
- The text must be in {lang_name} language, large and readable
- Professional typography with text shadow/outline for readability
- High contrast, bright colors that stand out in YouTube search results
- NO small text, NO cluttered design

{lang_code} context:
{trans_short}""",

        f"""Create a professional YouTube thumbnail image (16:9 aspect ratio, 1280x720).

The video is about:
{orig_short}

Requirements:
- Clean, modern design with bold visual impact
- Include a DIFFERENT short {lang_code} text/title (max 4-5 words) as overlay
- The text must be in {lang_name} language
- Use contrasting colors and dramatic lighting
- Eye-catching composition that makes viewers want to click
- Text should be large, bold, and easy to read even at small sizes

{lang_code} context:
{trans_short}""",
    ]

    for i, prompt in enumerate(thumbnail_prompts):
        try:
            contents = []
            if ref_image_part and i == 0:
                contents.append("Here is the original video thumbnail for reference. "
                                "Use it as inspiration for style and composition, "
                                f"but add {lang_code} text overlay and improve the design:")
                contents.append(ref_image_part)
            contents.append(prompt)

            # Retry with backoff for 503 errors
            response = None
            for attempt in range(5):
                try:
                    response = client.models.generate_content(
                        model=model_id,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            response_modalities=["TEXT", "IMAGE"],
                        ),
                    )
                    break
                except Exception as e:
                    error_str = str(e)
                    is_transient = "503" in error_str or "UNAVAILABLE" in error_str or "ServerError" in type(e).__name__
                    if is_transient and attempt < 4:
                        wait = (attempt + 1) * 15
                        logger.warning(f"Thumbnail {i + 1} API error, retrying in {wait}s")
                        time.sleep(wait)
                    else:
                        raise

            for part in response.parts:
                if part.inline_data is not None:
                    image = part.as_image()
                    thumb_path = os.path.join(output_dir, f"thumbnail_{i + 1}.png")
                    image.save(thumb_path)
                    saved_paths.append(thumb_path)
                    logger.info(f"Thumbnail {i + 1} saved: {thumb_path}")
                    break
            else:
                logger.warning(f"Thumbnail {i + 1}: no image in response")
                if response.text:
                    logger.info(f"Thumbnail {i + 1} text response: {response.text[:200]}")

        except Exception as e:
            logger.error(f"Thumbnail {i + 1} generation failed: {e}")

    return saved_paths


def generate_content(
    segments: list[dict],
    target_lang: str,
    source_url: str,
    output_dir: str,
    api_key: str,
    image_model_id: str,
    content_model_id: str,
) -> dict:
    """Main entry point: generate thumbnails + YouTube metadata.

    Steps:
    1. Extract plain text from transcript JSON → save as .txt files
    2. Use clean text for API calls (smaller, faster, cheaper)
    3. Generate thumbnails + metadata

    Returns dict with keys: thumbnails, metadata, metadata_file
    """
    result = {"thumbnails": [], "metadata": {}, "metadata_file": None}

    # Determine text field
    if target_lang == "vi-VN":
        text_field = "text_vi"
        script_name = "script_vi.txt"
    else:
        text_field = "text_jp"
        script_name = "script_jp.txt"

    # Step 1: Extract clean text from segments → .txt files
    script_original = extract_script_text(
        segments, "text",
        os.path.join(output_dir, "script_original.txt"),
    )
    script_translated = extract_script_text(
        segments, text_field,
        os.path.join(output_dir, script_name),
    )

    # Step 2: Fetch original thumbnail
    original_thumb = None
    if source_url:
        original_thumb = fetch_original_thumbnail(source_url, output_dir)

    # Step 3: Generate thumbnails (using clean text)
    logger.info("Generating thumbnail images...")
    result["thumbnails"] = generate_thumbnails(
        script_original=script_original,
        script_translated=script_translated,
        target_lang=target_lang,
        original_thumbnail_path=original_thumb,
        output_dir=output_dir,
        api_key=api_key,
        model_id=image_model_id,
    )

    # Step 4: Generate YouTube metadata (using clean text)
    logger.info("Generating YouTube metadata (title, description, hashtags)...")
    result["metadata"] = generate_youtube_metadata(
        script_original=script_original,
        script_translated=script_translated,
        target_lang=target_lang,
        source_url=source_url,
        api_key=api_key,
        model_id=content_model_id,
    )

    # Step 5: Save metadata to files
    metadata_path = os.path.join(output_dir, "youtube_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(result["metadata"], f, ensure_ascii=False, indent=2)
    result["metadata_file"] = metadata_path

    meta = result["metadata"]
    txt_path = os.path.join(output_dir, "youtube_post.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"TITLE:\n{meta.get('title', '')}\n\n")
        f.write(f"DESCRIPTION:\n{meta.get('description', '')}\n\n")
        f.write(f"HASHTAGS:\n{' '.join(meta.get('hashtags', []))}\n")
    logger.info(f"YouTube post content saved: {txt_path}")

    return result
