"""Run content generation (Step 8) for already-completed videos."""
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from src.content_generator import generate_content, generate_youtube_metadata, extract_script_text
from src.utils import setup_logging

logger = setup_logging("content_gen_batch")

OUTPUT_BASE = os.getenv("OUTPUT_DIR", "./output")
VN_DIR = os.path.join(OUTPUT_BASE, "VN")

def main():
    api_key = os.getenv("google_api_key", "")
    image_model = os.getenv("image_model_id", "gemini-3-pro-image-preview")
    content_model = os.getenv("content_model_id", "gemini-3.1-pro-preview")

    if not api_key:
        logger.error("google_api_key not set in .env")
        sys.exit(1)

    videos = json.load(open("list_video.json", encoding="utf-8"))
    success_videos = [v for v in videos if v.get("status") == "success"]

    logger.info(f"Running content generation for {len(success_videos)} videos")

    for i, v in enumerate(success_videos):
        vid = v["id"]
        url = v["video_url"]
        folder = os.path.join(VN_DIR, v["output_folder"])
        transcript_path = os.path.join(folder, "transcript_vi.json")

        logger.info(f"[{i+1}/{len(success_videos)}] ID={vid} | {url}")

        if not os.path.exists(transcript_path):
            logger.error(f"  Transcript not found: {transcript_path}")
            continue

        has_thumbnails = os.path.exists(os.path.join(folder, "thumbnail_1.png"))
        has_metadata = os.path.exists(os.path.join(folder, "youtube_metadata.json"))

        # Skip if both thumbnails and metadata already exist
        if has_thumbnails and has_metadata:
            # Verify metadata is valid (not fallback)
            try:
                meta = json.load(open(os.path.join(folder, "youtube_metadata.json"), encoding="utf-8"))
                if meta.get("title") != "Video":
                    logger.info(f"  Already complete, skipping")
                    continue
                logger.info(f"  Has fallback metadata, re-running metadata only")
            except (json.JSONDecodeError, OSError):
                pass

        if has_thumbnails:
            logger.info(f"  Thumbnails exist, running metadata only")

        segments = json.load(open(transcript_path, encoding="utf-8"))

        try:
            if has_thumbnails:
                # Only regenerate metadata
                script_orig_path = os.path.join(folder, "script_original.txt")
                script_vi_path = os.path.join(folder, "script_vi.txt")

                if os.path.exists(script_orig_path):
                    script_original = open(script_orig_path, encoding="utf-8").read()
                else:
                    script_original = extract_script_text(segments, "text", script_orig_path)

                if os.path.exists(script_vi_path):
                    script_translated = open(script_vi_path, encoding="utf-8").read()
                else:
                    script_translated = extract_script_text(segments, "text_vi", script_vi_path)

                metadata = generate_youtube_metadata(
                    script_original=script_original,
                    script_translated=script_translated,
                    target_lang="vi-VN",
                    source_url=url,
                    api_key=api_key,
                    model_id=content_model,
                )
                # Save metadata
                meta_path = os.path.join(folder, "youtube_metadata.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)

                txt_path = os.path.join(folder, "youtube_post.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(f"TITLE:\n{metadata.get('title', '')}\n\n")
                    f.write(f"DESCRIPTION:\n{metadata.get('description', '')}\n\n")
                    f.write(f"HASHTAGS:\n{' '.join(metadata.get('hashtags', []))}\n")

                logger.info(f"  Metadata regenerated: title='{metadata.get('title', '')[:50]}'")
            else:
                result = generate_content(
                    segments=segments,
                    target_lang="vi-VN",
                    source_url=url,
                    output_dir=folder,
                    api_key=api_key,
                    image_model_id=image_model,
                    content_model_id=content_model,
                )
                logger.info(f"  Thumbnails: {len(result['thumbnails'])}, Metadata: OK")
        except Exception as e:
            logger.error(f"  Failed: {e}")

    logger.info("Content generation batch complete")

if __name__ == "__main__":
    main()
