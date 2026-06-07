"""Vietnamese Video Dubbing Pipeline — CLI Entry Point.

Usage:
    python pipeline_vi.py                          # Reads VIDEO_URL from .env
    python pipeline_vi.py --url "https://..."      # Override with CLI arg
    python pipeline_vi.py --file video.mp4 --source-lang en
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime

import config
from src.utils import setup_logging, ensure_dir
from src.downloader import download_video
from src.audio_extractor import extract_audio
from src.transcriber import transcribe, save_transcript
from src.synthesizer_vi import synthesize_segment_vi
from src.audio_merger import merge_segments, fit_segments_to_timeline
from src.vocal_separator import separate_vocals
from src.video_merger import merge_video
from src.translate_pending import write_hint as _write_translate_pending_hint
from src.srt_generator import generate_srt
from src.content_generator import generate_content

logger = setup_logging("pipeline_vi")

LANG_MAP = {
    "en": "en-US",
    "ja": "ja-JP",
    "zh": "zh-CN",
    "en-US": "en-US",
    "ja-JP": "ja-JP",
    "zh-CN": "zh-CN",
    "zh-HK": "zh-HK",
    "zh-TW": "zh-TW",
}


def _notify(callback, step: str, status: str, **info) -> None:
    """Emit a progress notification, swallowing any callback error.

    Used by the Telegram bot worker; CLI mode passes callback=None.
    """
    if callback is None:
        return
    try:
        callback(step, status, **info)
    except Exception:
        logger.exception("progress_callback raised, ignoring")


def _build_timing_guide(report: dict, segments: list[dict], tts_results: list[dict]) -> dict:
    """Build a timing guide JSON for Vietnamese audio."""
    guide = {
        "session_id": report["session_id"],
        "source_url": report["source_url"],
        "target_language": "vi-VN",
        "summary": {
            "total_segments": report["total_segments"],
            "original_duration": report["total_original_duration"],
            "vi_duration": report["total_tts_duration"],
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
            "text_vi": seg.get("text_vi", ""),
            "start": seg["start"],
            "end": seg["end"],
            "original_duration": seg["duration"],
            "vi_duration": tts["actual_duration"],
            "diff_seconds": diff,
            "speed_adjusted": tts["speed_adjusted"],
            "rate_applied": tts.get("rate_applied", ""),
            "status": status,
            "edit_hint": f"VI {'dài' if diff > 0 else 'ngắn'} hơn {abs(diff):.1f}s"
                         if status != "OK" else "OK",
        })

    guide["summary"]["segments_need_edit"] = need_edit
    guide["summary"]["segments_ok"] = report["total_segments"] - need_edit

    return guide


def _get_default_vi_output_dir() -> str:
    """Get Vietnamese output directory: VIETNAMESE_OUTPUT_DIR or OUTPUT_DIR/VN."""
    if config.VIETNAMESE_OUTPUT_DIR:
        return config.VIETNAMESE_OUTPUT_DIR
    return os.path.join(config.OUTPUT_DIR, "VN")


def _ask_voice_gender() -> str:
    """Ask user to choose male or female voice. Returns voice ID."""
    print("\n" + "=" * 40)
    print("Chọn giọng đọc / Choose voice:")
    print("  1. Nam (Male)")
    print("  2. Nữ (Female)")
    print("=" * 40)

    while True:
        choice = input("Nhập 1 hoặc 2 (Enter 1 or 2): ").strip()
        if choice == "1":
            voice_id = config.VIETNAMESE_VOICEID_MALE
            logger.info(f"Selected: Male voice ({voice_id})")
            return voice_id
        elif choice == "2":
            voice_id = config.VIETNAMESE_VOICEID_FEMALE
            logger.info(f"Selected: Female voice ({voice_id})")
            return voice_id
        else:
            print("Vui lòng nhập 1 hoặc 2.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vietnamese Video Dubbing Pipeline: EN/JA → VI")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--url", help="YouTube/TikTok video URL (default: VIDEO_URL from .env)")
    group.add_argument("--file", help="Local video file path")

    parser.add_argument(
        "--source-lang",
        default=config.DEFAULT_SOURCE_LANG,
        help=f"Source language: en, ja, zh, en-US, ja-JP, zh-CN, zh-HK, zh-TW (default: {config.DEFAULT_SOURCE_LANG})",
    )
    parser.add_argument(
        "--voice",
        choices=["male", "female"],
        default=None,
        help="Voice gender: male or female (if not set, will ask interactively)",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip final video merge (only produce audio + SRT)",
    )
    parser.add_argument(
        "--output-dir",
        default=_get_default_vi_output_dir(),
        help=f"Output directory (default: ANKO Project/VN)",
    )
    parser.add_argument(
        "--resume",
        metavar="WORK_DIR",
        help="Resume an existing work directory. Steps whose outputs already exist are skipped.",
    )
    parser.add_argument(
        "--bg-mode",
        choices=["demucs", "duck", "none"],
        default="demucs",
        help="How to handle the original audio under the VI narration: "
             "'demucs' (default) runs vocal separation so only music/SFX remain — "
             "highest quality, ~7 min CPU per video. "
             "'duck' lowers the entire original_audio.wav by --bg-duck-db (default -12) "
             "and overlays VI on top — fast (no Demucs), original speech audible faintly. "
             "'none' merges VI on a silent base — legacy behavior, no original audio.",
    )
    parser.add_argument(
        "--bg-duck-db",
        type=float,
        default=-12.0,
        help="Gain (dB) applied to original audio in 'duck' mode. -12 dB ≈ 25%% volume "
             "(default), -6 dB ≈ 50%%, -20 dB ≈ 10%%. Ignored unless --bg-mode=duck.",
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
        help="Deprecated alias for --bg-mode=none. Kept for backwards compatibility.",
    )

    args = parser.parse_args()
    if args.no_bg_music:
        args.bg_mode = "none"

    if not args.url and not args.file and not args.resume:
        if config.VIETNAMESE_VIDEO_URL:
            args.url = config.VIETNAMESE_VIDEO_URL
            logger.info(f"Using VIETNAMESE_VIDEO_URL from .env: {args.url}")
        elif config.VIDEO_URL:
            args.url = config.VIDEO_URL
            logger.info(f"Using VIDEO_URL from .env: {args.url}")
        else:
            parser.error("No video specified. Use --url, --file, --resume, or set VIETNAMESE_VIDEO_URL in .env")

    # Resolve voice ID: CLI flag > .env Voice_type > interactive prompt
    if args.voice == "male":
        args.voice_id = config.VIETNAMESE_VOICEID_MALE
    elif args.voice == "female":
        args.voice_id = config.VIETNAMESE_VOICEID_FEMALE
    elif config.VOICE_TYPE == "male":
        args.voice_id = config.VIETNAMESE_VOICEID_MALE
        logger.info("Using VOICE_TYPE=male from .env")
    elif config.VOICE_TYPE == "female":
        args.voice_id = config.VIETNAMESE_VOICEID_FEMALE
        logger.info("Using VOICE_TYPE=female from .env")
    else:
        args.voice_id = _ask_voice_gender()

    return args


def _resolve_video(work_dir: str, url: str | None, file_path: str | None) -> str:
    """Locate the source video for this work_dir.

    Resume-friendly: if a prior run already downloaded/copied the source video
    into work_dir, reuse it instead of re-downloading. Skips any files whose
    name matches a pipeline output (dubbed_video*.mp4) so we don't mistake the
    rendered result for the source.

    If --file is passed, that takes precedence — useful when the user keeps
    the source outside work_dir.
    """
    if file_path:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")
        return file_path

    video_exts = (".mp4", ".mkv", ".webm", ".mov", ".avi")
    output_prefixes = ("dubbed_video",)
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


def run_pipeline_vi(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice_id: str,
    skip_video: bool,
    output_dir: str,
    resume_dir: str | None = None,
    bg_mode: str = "demucs",
    bg_duck_db: float = -12.0,
    upload_platforms: list[str] | None = None,
    public: bool = False,
    progress_callback=None,
) -> dict:
    start_time = time.time()

    lang_code = LANG_MAP.get(source_lang, source_lang)
    logger.info(f"Source language: {lang_code} → Vietnamese")

    # Resume an existing work_dir or create a new timestamped one
    if resume_dir:
        if not os.path.isdir(resume_dir):
            raise FileNotFoundError(f"Resume directory not found: {resume_dir}")
        work_dir = resume_dir
        folder_name = os.path.basename(os.path.normpath(work_dir))
        logger.info(f"Resuming work directory: {work_dir}")
    else:
        folder_name = datetime.now().strftime("%Y%m%d%H%M%S") + "_vi"
        work_dir = ensure_dir(os.path.join(output_dir, folder_name))
        logger.info(f"Output folder: {work_dir}")

    transcript_orig_path = os.path.join(work_dir, "transcript_original.json")
    transcript_vi_path = os.path.join(work_dir, "transcript_vi.json")
    audio_path = os.path.join(work_dir, "original_audio.wav")

    # --- Step 1: Download or use local file ---
    logger.info("=" * 60)
    logger.info("STEP 1: Acquiring video")
    _notify(progress_callback, "download", "running")
    video_path = _resolve_video(work_dir, url, file_path)
    logger.info(f"Video: {video_path}")
    _notify(progress_callback, "download", "ok", video_path=video_path)

    # --- Step 2: Extract audio ---
    logger.info("=" * 60)
    logger.info("STEP 2: Extracting audio")
    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
        logger.info(f"Reusing existing audio: {audio_path}")
        _notify(progress_callback, "extract_audio", "ok")
    else:
        _notify(progress_callback, "extract_audio", "running")
        extract_audio(video_path, audio_path)
        _notify(progress_callback, "extract_audio", "ok")

    # --- Step 2.5: Resolve background track for the dub merge ---
    background_path: str | None = None
    background_gain_db: float = 0.0
    if bg_mode == "demucs":
        logger.info("=" * 60)
        logger.info("STEP 2.5: Separating vocals from original audio (Demucs)")
        _notify(progress_callback, "vocal_sep", "running")
        sep = separate_vocals(audio_path, work_dir)
        background_path = sep.get("no_vocals")
        if background_path is None:
            logger.warning(
                "Vocal separation unavailable — dubbed audio will use a silent base"
            )
        _notify(progress_callback, "vocal_sep", "ok")
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
    logger.info("STEP 3: Transcribing audio (ASR)")
    if os.path.exists(transcript_orig_path):
        logger.info(f"Reusing existing transcript: {transcript_orig_path}")
        with open(transcript_orig_path, encoding="utf-8") as f:
            segments = json.load(f)
        logger.info(f"Loaded {len(segments)} segments from cache")
        _notify(progress_callback, "asr", "ok", n_segments=len(segments))
    else:
        _notify(progress_callback, "asr", "running")
        segments = transcribe(audio_path, lang_code)
        save_transcript(segments, transcript_orig_path)
        generate_srt(segments, os.path.join(work_dir, "transcript_original.srt"), text_field="text")
        logger.info(f"Transcribed {len(segments)} segments")
        _notify(progress_callback, "asr", "ok", n_segments=len(segments))

    # --- Step 4: Translate to Vietnamese ---
    logger.info("=" * 60)
    logger.info("STEP 4: Translating to Vietnamese")
    if os.path.exists(transcript_vi_path):
        logger.info(f"Reusing existing translation: {transcript_vi_path}")
        with open(transcript_vi_path, encoding="utf-8") as f:
            segments = json.load(f)
    else:
        _write_translate_pending_hint(work_dir, "vi-VN", source_lang)
        logger.warning("Translation pending — see TRANSLATE_PENDING.txt in work dir")
        _notify(progress_callback, "translate_pending", "ok", work_dir=work_dir)
        return {"status": "translate_pending", "work_dir": work_dir}

    # --- Step 5: TTS for each segment (LucyLab API) ---
    logger.info("=" * 60)
    logger.info("STEP 5: Synthesizing Vietnamese audio (LucyLab TTS)")
    _notify(progress_callback, "tts", "running")
    seg_dir = ensure_dir(os.path.join(work_dir, "segments"))
    tts_results = []
    from pydub import AudioSegment as _ASeg

    for seg in segments:
        seg_path = os.path.join(seg_dir, f"seg_{seg['id']:03d}.wav")
        if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
            cached = _ASeg.from_wav(seg_path)
            result = {
                "path": seg_path,
                "actual_duration": round(len(cached) / 1000.0, 3),
                "speed_adjusted": False,
                "rate_applied": "cached",
            }
            logger.info(
                f"  Segment {seg['id']}: cached ({result['actual_duration']:.1f}s, "
                f"target {seg['duration']:.1f}s)"
            )
        else:
            result = synthesize_segment_vi(
                text_vi=seg["text_vi"],
                output_path=seg_path,
                target_duration=seg["duration"],
                voice_id=voice_id,
            )
            logger.info(
                f"  Segment {seg['id']}: {result['actual_duration']:.1f}s "
                f"(target: {seg['duration']:.1f}s, speed: {result['rate_applied']})"
            )
        tts_results.append(result)
    _notify(progress_callback, "tts", "ok", n_segments=len(tts_results))

    # --- Step 6: Slow down + Fit-to-timeline + Merge audio ---
    logger.info("=" * 60)
    _notify(progress_callback, "merge_audio", "running")
    slow_factor = config.AUDIO_SLOW_FACTOR
    total_duration = max(seg["end"] for seg in segments) + 1.0 if segments else 0

    if slow_factor < 1.0:
        slow_pct = round((1.0 - slow_factor) * 100)
        logger.info(f"STEP 6a: Slowing segments {slow_pct}% (atempo={slow_factor})")
        slow_dir = ensure_dir(os.path.join(work_dir, f"segments_slow{slow_pct}"))
        for seg in segments:
            src = os.path.join(seg_dir, f"seg_{seg['id']:03d}.wav")
            dst = os.path.join(slow_dir, f"seg_{seg['id']:03d}.wav")
            if os.path.exists(src):
                subprocess.run(
                    ["ffmpeg", "-y", "-i", src, "-filter:a", f"atempo={slow_factor}", dst],
                    capture_output=True, text=True,
                )
        pre_fit_dir = slow_dir
    else:
        pre_fit_dir = seg_dir

    logger.info("STEP 6b: Fitting segments to timeline (avoid overlap)")
    fit_dir = ensure_dir(os.path.join(work_dir, "segments_fit"))
    fit_adjustments = fit_segments_to_timeline(segments, pre_fit_dir, fit_dir)

    fit_log_path = os.path.join(work_dir, "fit_adjustments.json")
    with open(fit_log_path, "w", encoding="utf-8") as f:
        json.dump(fit_adjustments, f, ensure_ascii=False, indent=2)

    logger.info("STEP 6c: Merging audio segments")
    merged_audio_path = os.path.join(work_dir, "audio_vi_full.wav")
    merge_segments(
        segments, fit_dir, merged_audio_path, total_duration,
        background_path=background_path,
        background_gain_db=background_gain_db,
    )
    _notify(progress_callback, "merge_audio", "ok")

    # --- Step 7: Merge video (optional) ---
    dubbed_video_path = None
    if not skip_video:
        logger.info("=" * 60)
        logger.info("STEP 7: Creating dubbed video")
        _notify(progress_callback, "merge_video", "running")
        dubbed_video_path = os.path.join(work_dir, "dubbed_video.mp4")
        merge_video(video_path, merged_audio_path, dubbed_video_path)
        _notify(progress_callback, "merge_video", "ok", video_path=dubbed_video_path)

    # --- Step 8: Generate metadata + thumbnail via Claude Code subprocess ---
    # Claude path (subscription only, no API cost) → falls back to Gemini if
    # claude CLI is not available AND google_api_key is set.
    logger.info("=" * 60)
    logger.info("STEP 8: Generating YouTube metadata + thumbnail")
    _notify(progress_callback, "metadata", "running")
    content_result = {"thumbnails": [], "metadata": {}}
    metadata_ok = False
    try:
        from src.content_via_claude import (
            generate_metadata_via_claude,
            generate_thumbnail_via_claude,
            ContentError,
        )
        try:
            generate_metadata_via_claude(work_dir)
            logger.info("  [OK] Metadata via Claude")
            metadata_ok = True
        except ContentError as e:
            logger.warning(f"  Metadata via Claude failed: {e}")
        try:
            generate_thumbnail_via_claude(work_dir)
            logger.info("  [OK] Thumbnail via Claude + Higgsfield")
        except ContentError as e:
            logger.warning(f"  Thumbnail via Claude failed (non-fatal): {e}")
    except Exception as e:
        logger.error(f"Claude content generation crashed: {e}")

    # Fallback: if Claude didn't produce metadata and Gemini key is available,
    # use legacy Gemini path so the upload still has title/description.
    if not metadata_ok and config.GOOGLE_API_KEY:
        logger.info("  Falling back to Gemini for metadata")
        try:
            generate_content(
                segments=segments,
                target_lang="vi-VN",
                source_url=url,
                output_dir=work_dir,
                api_key=config.GOOGLE_API_KEY,
                image_model_id=config.IMAGE_MODEL_ID,
                content_model_id=config.CONTENT_MODEL_ID,
            )
            metadata_ok = True
        except Exception as e:
            logger.error(f"Gemini fallback also failed: {e}")

    if metadata_ok:
        _notify(progress_callback, "metadata", "ok")
    else:
        _notify(progress_callback, "metadata", "fail", error="metadata generation failed")

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
            step_key = f"upload:{platform_name}"
            if res.success:
                logger.info(f"  [OK] {platform_name}: {res.url}")
                _notify(progress_callback, step_key, "ok", url=res.url)
            else:
                logger.error(f"  [FAIL] {platform_name}: {res.error} - {res.error_message}")
                _notify(progress_callback, step_key, "fail", error=res.error or "unknown")
    elif upload_platforms and not dubbed_video_path:
        logger.warning("STEP 9 skipped: --upload requested but --skip-video produced no video file")

    # --- Generate report ---
    elapsed = time.time() - start_time
    report = {
        "session_id": folder_name,
        "source_url": url,
        "source_language": lang_code,
        "target_language": "vi-VN",
        "voice_id": voice_id,
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
            "transcript_vi_json": os.path.join(work_dir, "transcript_vi.json"),
            "transcript_vi_srt": os.path.join(work_dir, "transcript_vi.srt"),
            "audio_vi_full": merged_audio_path,
            "dubbed_video": dubbed_video_path,
            "thumbnails": content_result.get("thumbnails", []),
            "youtube_metadata": content_result.get("metadata_file"),
        },
    }

    report_path = os.path.join(work_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # --- Generate timing guide ---
    timing_guide = _build_timing_guide(report, segments, tts_results)
    timing_path = os.path.join(work_dir, "timing_guide.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing_guide, f, ensure_ascii=False, indent=2)
    logger.info(f"Timing guide: {timing_path}")

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE (Vietnamese)")
    logger.info(f"  Output:    {work_dir}")
    logger.info(f"  Segments:  {report['total_segments']}")
    logger.info(f"  Duration:  {report['total_original_duration']:.1f}s original, "
                f"{report['total_tts_duration']:.1f}s VI audio")
    logger.info(f"  Adjusted:  {report['segments_speed_adjusted']} segments speed-adjusted")
    logger.info(f"  Time:      {elapsed:.1f}s")
    logger.info("=" * 60)

    return report


def main():
    args = parse_args()
    try:
        run_pipeline_vi(
            url=args.url,
            file_path=args.file,
            source_lang=args.source_lang,
            voice_id=args.voice_id,
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
