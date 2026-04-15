"""Video Dubbing Pipeline — CLI Entry Point.

Usage:
    python pipeline.py --url "https://youtube.com/watch?v=xxx" --source-lang en
    python pipeline.py --file video.mp4 --source-lang vi
    python pipeline.py --url "..." --source-lang en --voice ja-JP-NanamiNeural --skip-video
"""
import argparse
import json
import os
import sys
import time

import config
from src.utils import setup_logging, ensure_dir
from src.downloader import download_video, get_video_id
from src.audio_extractor import extract_audio
from src.transcriber import transcribe, save_transcript
from src.translator import translate_segments
from src.synthesizer import synthesize_segment
from src.audio_merger import merge_segments
from src.video_merger import merge_video
from src.srt_generator import generate_srt

logger = setup_logging("pipeline")

LANG_MAP = {
    "en": "en-US",
    "vi": "vi-VN",
    "en-US": "en-US",
    "vi-VN": "vi-VN",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Video Dubbing Pipeline: EN/VI → JP")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="YouTube/TikTok video URL")
    group.add_argument("--file", help="Local video file path")

    parser.add_argument(
        "--source-lang",
        default=config.DEFAULT_SOURCE_LANG,
        help=f"Source language: en, vi, en-US, vi-VN (default: {config.DEFAULT_SOURCE_LANG})",
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
    return parser.parse_args()


def run_pipeline(
    url: str | None,
    file_path: str | None,
    source_lang: str,
    voice: str,
    skip_video: bool,
    output_dir: str,
) -> dict:
    start_time = time.time()

    lang_code = LANG_MAP.get(source_lang, source_lang)
    logger.info(f"Source language: {lang_code}")

    # --- Step 1: Download or use local file ---
    logger.info("=" * 60)
    logger.info("STEP 1: Acquiring video")
    if url:
        video_id = get_video_id(url)
        work_dir = ensure_dir(os.path.join(output_dir, video_id))
        video_path = download_video(url, work_dir)
    else:
        video_path = file_path
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        video_id = os.path.splitext(os.path.basename(video_path))[0]
        work_dir = ensure_dir(os.path.join(output_dir, video_id))
    logger.info(f"Video: {video_path}")

    # --- Step 2: Extract audio ---
    logger.info("=" * 60)
    logger.info("STEP 2: Extracting audio")
    audio_path = os.path.join(work_dir, "original_audio.wav")
    extract_audio(video_path, audio_path)

    # --- Step 3: Speech-to-Text (ASR) ---
    logger.info("=" * 60)
    logger.info("STEP 3: Transcribing audio (ASR)")
    segments = transcribe(audio_path, lang_code)
    save_transcript(segments, os.path.join(work_dir, "transcript_original.json"))
    generate_srt(segments, os.path.join(work_dir, "transcript_original.srt"), text_field="text")
    logger.info(f"Transcribed {len(segments)} segments")

    # --- Step 4: Translate to Japanese ---
    logger.info("=" * 60)
    logger.info("STEP 4: Translating to Japanese")
    segments = translate_segments(segments, lang_code)
    save_transcript(segments, os.path.join(work_dir, "transcript_jp.json"))
    generate_srt(segments, os.path.join(work_dir, "transcript_jp.srt"), text_field="text_jp")

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
    merge_segments(segments, seg_dir, merged_audio_path, total_duration)

    # --- Step 7: Merge video (optional) ---
    dubbed_video_path = None
    if not skip_video:
        logger.info("=" * 60)
        logger.info("STEP 7: Creating dubbed video")
        dubbed_video_path = os.path.join(work_dir, "dubbed_video.mp4")
        merge_video(video_path, merged_audio_path, dubbed_video_path)

    # --- Generate report ---
    elapsed = time.time() - start_time
    report = {
        "video_id": video_id,
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
        },
    }

    report_path = os.path.join(work_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

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
        )
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
