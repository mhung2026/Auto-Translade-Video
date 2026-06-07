"""Video Dubbing Pipeline — CLI Entry Point.

Usage:
    python pipeline.py                          # Reads VIDEO_URL from .env
    python pipeline.py --url "https://..."      # Override with CLI arg
    python pipeline.py --file video.mp4 --source-lang vi
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import config
from src.utils import setup_logging, ensure_dir
from src.downloader import download_video
from src.audio_extractor import extract_audio
from src.transcriber import transcribe, save_transcript
from src.synthesizer import synthesize_segment
from src.translate_pending import write_hint as _write_translate_pending_hint
from src.audio_merger import merge_segments
from src.vocal_separator import separate_vocals
from src.video_merger import merge_video
from src.srt_generator import generate_srt
from src.content_generator import generate_content

logger = setup_logging("pipeline")

LANG_MAP = {
    "en": "en-US",
    "vi": "vi-VN",
    "zh": "zh-CN",
    "en-US": "en-US",
    "vi-VN": "vi-VN",
    "zh-CN": "zh-CN",
    "zh-HK": "zh-HK",
    "zh-TW": "zh-TW",
}


def _build_timing_guide(report: dict, segments: list[dict], tts_results: list[dict]) -> dict:
    """Build a timing guide JSON showing differences between original and JP audio per segment.

    Helps user quickly identify which segments need manual adjustment in CapCut.
    """
    guide = {
        "session_id": report["session_id"],
        "source_url": report["source_url"],
        "summary": {
            "total_segments": report["total_segments"],
            "original_duration": report["total_original_duration"],
            "jp_duration": report["total_tts_duration"],
            "ratio": round(report["total_tts_duration"] / report["total_original_duration"], 2)
                     if report["total_original_duration"] > 0 else 0,
            "segments_need_edit": 0,
            "segments_ok": 0,
        },
        "segments": [],
    }

    need_edit = 0
    for seg, tts in zip(segments, tts_results):
        diff = round(tts["actual_duration"] - seg["duration"], 2)

        # OK if JP audio within ±30% of original duration
        if abs(diff) <= seg["duration"] * 0.3:
            status = "OK"
        elif diff > 0:
            status = "TOO_LONG"
            need_edit += 1
        else:
            status = "TOO_SHORT"
            need_edit += 1

        guide["segments"].append({
            "id": seg["id"],
            "text_original": seg["text"],
            "text_jp": seg.get("text_jp", ""),
            "start": seg["start"],
            "end": seg["end"],
            "original_duration": seg["duration"],
            "jp_duration": tts["actual_duration"],
            "diff_seconds": diff,
            "speed_adjusted": tts["speed_adjusted"],
            "rate_applied": tts.get("rate_applied", ""),
            "status": status,
            "edit_hint": f"JP {'dài' if diff > 0 else 'ngắn'} hơn {abs(diff):.1f}s"
                         if status != "OK" else "OK",
        })

    guide["summary"]["segments_need_edit"] = need_edit
    guide["summary"]["segments_ok"] = report["total_segments"] - need_edit

    return guide


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Video Dubbing Pipeline: EN/VI → JP")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--url", help="YouTube/TikTok video URL (default: VIDEO_URL from .env)")
    group.add_argument("--file", help="Local video file path")

    parser.add_argument(
        "--source-lang",
        default=config.DEFAULT_SOURCE_LANG,
        help=f"Source language: en, vi, zh, en-US, vi-VN, zh-CN, zh-HK, zh-TW (default: {config.DEFAULT_SOURCE_LANG})",
    )
    parser.add_argument(
        "--voice",
        default=config.TTS_VOICE,
        help=f"TTS voice name (default: {config.TTS_VOICE})",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip final video merge (only produce audio + SRT)",
    )
    parser.add_argument(
        "--output-dir",
        default=config.OUTPUT_DIR,
        help=f"Output directory (default: {config.OUTPUT_DIR})",
    )
    parser.add_argument(
        "--bg-mode",
        choices=["demucs", "duck", "none"],
        default="demucs",
        help="How to handle the original audio under the JP narration: "
             "'demucs' (default) runs vocal separation; 'duck' lowers original_audio.wav "
             "by --bg-duck-db (default -12) and overlays JP — fast, no Demucs; "
             "'none' uses a silent base.",
    )
    parser.add_argument(
        "--bg-duck-db",
        type=float,
        default=-12.0,
        help="Gain (dB) applied to original audio in 'duck' mode (default -12 dB ≈ 25%%).",
    )
    parser.add_argument(
        "--upload",
        metavar="PLATFORMS",
        default="",
        help="Comma-separated platforms to publish to after dub (e.g. 'youtube,facebook'). "
             "Default: don't upload.",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Upload as PUBLIC. Default: private/draft (review manually before publishing).",
    )
    parser.add_argument(
        "--no-bg-music",
        action="store_true",
        help="Deprecated alias for --bg-mode=none.",
    )
    parser.add_argument(
        "--resume",
        metavar="WORK_DIR",
        help="Resume a previous run inside the given work directory. "
             "Skips already-completed steps based on cached artifacts.",
    )

    args = parser.parse_args()
    if args.no_bg_music:
        args.bg_mode = "none"

    # Fallback: if no --url and no --file, read VIDEO_URL from .env.
    # On --resume, neither is required (the cached video sits in work_dir).
    if not args.url and not args.file and not args.resume:
        if config.VIDEO_URL:
            args.url = config.VIDEO_URL
            logger.info(f"Using VIDEO_URL from .env: {args.url}")
        else:
            parser.error("No video specified. Use --url, --file, --resume, or set VIDEO_URL in .env")

    return args


def _resolve_video(work_dir: str, url: str | None, file_path: str | None) -> str:
    """Locate the source video for this work_dir.

    Resume-friendly: reuse a previously downloaded/copied video in work_dir
    instead of re-downloading. Files matching ``dubbed_video*.mp4`` are
    treated as pipeline output, not source.
    """
    if file_path:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")
        return file_path

    video_exts = (".mp4", ".mkv", ".webm", ".mov", ".avi")
    output_prefixes = ("dubbed_video",)
    if os.path.isdir(work_dir):
        for f in sorted(os.listdir(work_dir)):
            lower = f.lower()
            if not lower.endswith(video_exts):
                continue
            if any(lower.startswith(prefix) for prefix in output_prefixes):
                continue
            cached = os.path.join(work_dir, f)
            logger.info(f"Reusing existing video: {cached}")
            return cached

    if url:
        return download_video(url, work_dir)

    raise RuntimeError(
        f"No source video found in {work_dir} and no --url/--file given. "
        "Pass --file <path> on resume if the original is outside work_dir."
    )


def run_pipeline(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice: str,
    skip_video: bool,
    output_dir: str,
    resume_dir: str | None = None,
    bg_mode: str = "demucs",
    bg_duck_db: float = -12.0,
    upload_platforms: list[str] | None = None,
    public: bool = False,
) -> dict:
    start_time = time.time()

    lang_code = LANG_MAP.get(source_lang, source_lang)
    logger.info(f"Source language: {lang_code}")

    if resume_dir:
        if not os.path.isdir(resume_dir):
            raise FileNotFoundError(f"Resume directory not found: {resume_dir}")
        work_dir = resume_dir
        folder_name = os.path.basename(os.path.normpath(work_dir))
        logger.info(f"Resuming work directory: {work_dir}")
    else:
        folder_name = datetime.now().strftime("%Y%m%d%H%M%S")
        work_dir = ensure_dir(os.path.join(output_dir, folder_name))
        logger.info(f"Output folder: {work_dir}")

    transcript_orig_path = os.path.join(work_dir, "transcript_original.json")
    transcript_jp_path = os.path.join(work_dir, "transcript_jp.json")
    audio_path = os.path.join(work_dir, "original_audio.wav")

    # --- Step 1: Download or use local file ---
    logger.info("=" * 60)
    logger.info("STEP 1: Acquiring video")
    video_path = _resolve_video(work_dir, url, file_path)
    logger.info(f"Video: {video_path}")

    # --- Step 2: Extract audio ---
    logger.info("=" * 60)
    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        logger.info(f"STEP 2: Reusing existing extracted audio: {audio_path}")
    else:
        logger.info("STEP 2: Extracting audio")
        extract_audio(video_path, audio_path)

    # --- Step 2.5: Resolve background track for the dub merge ---
    background_path: str | None = None
    background_gain_db: float = 0.0
    if bg_mode == "demucs":
        logger.info("=" * 60)
        logger.info("STEP 2.5: Separating vocals from original audio (Demucs)")
        sep = separate_vocals(audio_path, work_dir)
        background_path = sep.get("no_vocals")
        if background_path is None:
            logger.warning(
                "Vocal separation unavailable — dubbed audio will use a silent base"
            )
    elif bg_mode == "duck":
        logger.info("=" * 60)
        logger.info(
            f"STEP 2.5: Ducking original audio by {bg_duck_db:+.1f} dB "
            "(no vocal separation)"
        )
        background_path = audio_path
        background_gain_db = bg_duck_db
    elif bg_mode == "none":
        logger.info("STEP 2.5 skipped: --bg-mode=none, dubbed audio uses silent base")

    # --- Step 3: Speech-to-Text (ASR) ---
    logger.info("=" * 60)
    if os.path.exists(transcript_orig_path):
        logger.info(f"STEP 3: Reusing existing transcript: {transcript_orig_path}")
        with open(transcript_orig_path, encoding="utf-8") as f:
            segments = json.load(f)
    else:
        logger.info("STEP 3: Transcribing audio (ASR)")
        segments = transcribe(audio_path, lang_code)
        save_transcript(segments, transcript_orig_path)
        generate_srt(segments, os.path.join(work_dir, "transcript_original.srt"), text_field="text")
    logger.info(f"Transcribed {len(segments)} segments")

    # --- Step 4: Translate to Japanese (manual via skill or web AI) ---
    logger.info("=" * 60)
    logger.info("STEP 4: Loading Japanese translation")
    if os.path.exists(transcript_jp_path):
        logger.info(f"Reusing existing translation: {transcript_jp_path}")
        with open(transcript_jp_path, encoding="utf-8") as f:
            segments = json.load(f)
    else:
        _write_translate_pending_hint(work_dir, "ja-JP", source_lang)
        logger.warning("Translation pending — see TRANSLATE_PENDING.txt in work dir")
        return {"status": "translate_pending", "work_dir": work_dir}

    # --- Step 5: TTS for each segment ---
    logger.info("=" * 60)
    logger.info("STEP 5: Synthesizing Japanese audio (TTS)")
    seg_dir = ensure_dir(os.path.join(work_dir, "segments"))
    tts_results = []
    for seg in segments:
        seg_path = os.path.join(seg_dir, f"seg_{seg['id']:03d}.wav")
        result = synthesize_segment(
            text_jp=seg["text_jp"],
            output_path=seg_path,
            target_duration=seg["duration"],
            voice=voice,
        )
        tts_results.append(result)
        logger.info(
            f"  Segment {seg['id']}: {result['actual_duration']:.1f}s "
            f"(target: {seg['duration']:.1f}s, adjusted: {result['speed_adjusted']})"
        )

    # --- Step 6: Merge audio ---
    logger.info("=" * 60)
    logger.info("STEP 6: Merging audio segments")
    total_duration = max(seg["end"] for seg in segments) + 1.0 if segments else 0
    merged_audio_path = os.path.join(work_dir, "audio_jp_full.wav")
    merge_segments(
        segments, seg_dir, merged_audio_path, total_duration,
        background_path=background_path,
        background_gain_db=background_gain_db,
    )

    # --- Step 7: Merge video (optional) ---
    dubbed_video_path = None
    if not skip_video:
        logger.info("=" * 60)
        logger.info("STEP 7: Creating dubbed video")
        dubbed_video_path = os.path.join(work_dir, "dubbed_video.mp4")
        merge_video(video_path, merged_audio_path, dubbed_video_path)

    # --- Step 8: Generate thumbnails + YouTube metadata ---
    content_result = {"thumbnails": [], "metadata": {}}
    if config.GOOGLE_API_KEY:
        logger.info("=" * 60)
        logger.info("STEP 8: Generating thumbnails & YouTube metadata")
        try:
            content_result = generate_content(
                segments=segments,
                target_lang="ja-JP",
                source_url=url,
                output_dir=work_dir,
                api_key=config.GOOGLE_API_KEY,
                image_model_id=config.IMAGE_MODEL_ID,
                content_model_id=config.CONTENT_MODEL_ID,
            )
            logger.info(f"  Thumbnail prompts: {content_result.get('thumbnail_prompts_file', 'N/A')}")
            logger.info(f"  Metadata: {content_result.get('metadata_file', 'N/A')}")
        except Exception as e:
            logger.error(f"Content generation failed (non-fatal): {e}")
    else:
        logger.info("Skipping thumbnail/metadata generation (GOOGLE_API_KEY not set)")

    # --- Step 9: Publish to YouTube / Facebook ---
    if upload_platforms and dubbed_video_path:
        logger.info("=" * 60)
        logger.info(f"STEP 9: Publishing to {', '.join(upload_platforms)} "
                    f"(privacy={'public' if public else 'private/draft'})")
        from src.publishers import publish
        publish_results = publish(
            work_dir=work_dir,
            video_path=dubbed_video_path,
            platforms=upload_platforms,
            public=public,
        )
        for platform_name, res in publish_results.items():
            if res.success:
                logger.info(f"  [OK] {platform_name}: {res.url}")
            else:
                logger.error(f"  [FAIL] {platform_name}: {res.error} - {res.error_message}")
    elif upload_platforms and not dubbed_video_path:
        logger.warning("STEP 9 skipped: --upload requested but --skip-video produced no video file")

    # --- Generate report ---
    elapsed = time.time() - start_time
    report = {
        "session_id": folder_name,
        "source_url": url,
        "source_language": lang_code,
        "voice": voice,
        "total_segments": len(segments),
        "total_original_duration": round(sum(s["duration"] for s in segments), 3),
        "total_tts_duration": round(sum(r["actual_duration"] for r in tts_results), 3),
        "segments_speed_adjusted": sum(1 for r in tts_results if r["speed_adjusted"]),
        "processing_time_seconds": round(elapsed, 1),
        "output_dir": work_dir,
        "files": {
            "original_audio": audio_path,
            "transcript_original_json": os.path.join(work_dir, "transcript_original.json"),
            "transcript_original_srt": os.path.join(work_dir, "transcript_original.srt"),
            "transcript_jp_json": os.path.join(work_dir, "transcript_jp.json"),
            "transcript_jp_srt": os.path.join(work_dir, "transcript_jp.srt"),
            "audio_jp_full": merged_audio_path,
            "dubbed_video": dubbed_video_path,
            "thumbnails": content_result.get("thumbnails", []),
            "youtube_metadata": content_result.get("metadata_file"),
        },
    }

    report_path = os.path.join(work_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # --- Generate timing guide for CapCut editing ---
    timing_guide = _build_timing_guide(report, segments, tts_results)
    timing_path = os.path.join(work_dir, "timing_guide.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing_guide, f, ensure_ascii=False, indent=2)
    logger.info(f"Timing guide: {timing_path}")

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Output:    {work_dir}")
    logger.info(f"  Segments:  {report['total_segments']}")
    logger.info(f"  Duration:  {report['total_original_duration']:.1f}s original, "
                f"{report['total_tts_duration']:.1f}s JP audio")
    logger.info(f"  Adjusted:  {report['segments_speed_adjusted']} segments sped up")
    logger.info(f"  Time:      {elapsed:.1f}s")
    logger.info("=" * 60)

    return report


def main():
    args = parse_args()
    try:
        run_pipeline(
            url=args.url,
            file_path=args.file,
            source_lang=args.source_lang,
            voice=args.voice,
            skip_video=args.skip_video,
            output_dir=args.output_dir,
            resume_dir=args.resume,
            bg_mode=args.bg_mode,
            bg_duck_db=args.bg_duck_db,
            upload_platforms=[p.strip() for p in args.upload.split(",") if p.strip()],
            public=args.public,
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
