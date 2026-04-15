import os
from pydub import AudioSegment
from pydub.generators import Sine
from src.audio_merger import merge_segments


def _make_segment_file(path: str, duration_ms: int = 1000):
    tone = Sine(440).to_audio_segment(duration=duration_ms)
    tone.export(path, format="wav")


def test_merge_segments_basic(tmp_path):
    seg_dir = str(tmp_path / "segments")
    os.makedirs(seg_dir)

    _make_segment_file(os.path.join(seg_dir, "seg_001.wav"), 500)
    _make_segment_file(os.path.join(seg_dir, "seg_002.wav"), 800)

    segments = [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0},
        {"id": 2, "start": 2.0, "end": 3.5, "duration": 1.5},
    ]
    total_duration = 5.0
    output_path = str(tmp_path / "merged.wav")

    result = merge_segments(segments, seg_dir, output_path, total_duration)
    assert os.path.exists(result)

    audio = AudioSegment.from_wav(result)
    assert abs(len(audio) / 1000.0 - total_duration) < 0.1


def test_merge_segments_empty(tmp_path):
    seg_dir = str(tmp_path / "segments")
    os.makedirs(seg_dir)
    output_path = str(tmp_path / "merged.wav")

    result = merge_segments([], seg_dir, output_path, total_duration=3.0)
    assert os.path.exists(result)
    audio = AudioSegment.from_wav(result)
    assert abs(len(audio) / 1000.0 - 3.0) < 0.1
