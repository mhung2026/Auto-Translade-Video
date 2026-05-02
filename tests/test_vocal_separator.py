import os
from unittest import mock

from pydub import AudioSegment
from pydub.generators import Sine

from src import vocal_separator


def _make_wav(path: str, duration_ms: int = 200):
    Sine(220).to_audio_segment(duration=duration_ms).export(path, format="wav")


def test_separate_vocals_short_circuits_when_outputs_exist(tmp_path):
    work_dir = str(tmp_path)
    _make_wav(os.path.join(work_dir, "vocals.wav"))
    _make_wav(os.path.join(work_dir, "no_vocals.wav"))
    input_wav = str(tmp_path / "original_audio.wav")
    _make_wav(input_wav)

    with mock.patch("src.vocal_separator._run_demucs") as run, \
         mock.patch("src.vocal_separator.subprocess.run") as ffmpeg:
        result = vocal_separator.separate_vocals(input_wav, work_dir)

    run.assert_not_called()
    ffmpeg.assert_not_called()
    assert result["no_vocals"] == os.path.join(work_dir, "no_vocals.wav")
    assert result["vocals"] == os.path.join(work_dir, "vocals.wav")


def test_separate_vocals_returns_none_when_input_missing(tmp_path):
    work_dir = str(tmp_path)
    result = vocal_separator.separate_vocals(
        str(tmp_path / "missing.wav"), work_dir
    )
    assert result == {"vocals": None, "no_vocals": None}


def test_separate_vocals_returns_none_when_demucs_raises(tmp_path):
    work_dir = str(tmp_path)
    input_wav = str(tmp_path / "original_audio.wav")
    _make_wav(input_wav)

    def boom(*args, **kwargs):
        raise RuntimeError("model load failed")

    with mock.patch("src.vocal_separator._run_demucs", side_effect=boom):
        result = vocal_separator.separate_vocals(input_wav, work_dir)

    assert result == {"vocals": None, "no_vocals": None}
    assert not os.path.exists(os.path.join(work_dir, "no_vocals.wav"))
    # Raw scratch files should be cleaned up after a failed run
    assert not os.path.exists(os.path.join(work_dir, "_vocals_raw.wav"))
    assert not os.path.exists(os.path.join(work_dir, "_no_vocals_raw.wav"))


def test_separate_vocals_normalizes_and_cleans_up(tmp_path):
    """Mocks a successful Demucs run plus the ffmpeg normalize step and
    verifies the final stems land in work_dir while raw scratch files are
    removed."""
    work_dir = str(tmp_path / "work")
    os.makedirs(work_dir)
    input_wav = str(tmp_path / "original_audio.wav")
    _make_wav(input_wav)

    def fake_demucs(src, vocals_out, no_vocals_out, model_name):
        _make_wav(vocals_out)
        _make_wav(no_vocals_out)

    captured = []

    def fake_ffmpeg(cmd, **kwargs):
        captured.append(cmd)
        src = cmd[cmd.index("-i") + 1]
        dst = cmd[-1]
        AudioSegment.from_wav(src).export(dst, format="wav")
        return mock.Mock(returncode=0, stderr="")

    with mock.patch("src.vocal_separator._run_demucs", side_effect=fake_demucs), \
         mock.patch("src.vocal_separator.subprocess.run", side_effect=fake_ffmpeg):
        result = vocal_separator.separate_vocals(input_wav, work_dir)

    assert result["no_vocals"] == os.path.join(work_dir, "no_vocals.wav")
    assert result["vocals"] == os.path.join(work_dir, "vocals.wav")
    assert os.path.exists(result["no_vocals"])
    assert os.path.exists(result["vocals"])
    assert not os.path.exists(os.path.join(work_dir, "_vocals_raw.wav"))
    assert not os.path.exists(os.path.join(work_dir, "_no_vocals_raw.wav"))
    assert sum(1 for c in captured if c[0] == "ffmpeg") == 2
