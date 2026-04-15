from src.utils import format_timestamp, setup_logging

logger = setup_logging("srt_generator")


def generate_srt(segments: list[dict], output_path: str, text_field: str = "text") -> str:
    lines = []
    for i, seg in enumerate(segments, start=1):
        start_ts = format_timestamp(seg["start"])
        end_ts = format_timestamp(seg["end"])
        text = seg[text_field]
        lines.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"SRT written: {output_path} ({len(segments)} entries)")
    return output_path
