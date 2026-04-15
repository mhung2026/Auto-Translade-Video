import os
from src.srt_generator import generate_srt


def test_generate_srt_original_text(tmp_path):
    segments = [
        {"id": 1, "text": "Hello everyone", "start": 0.5, "end": 3.2, "duration": 2.7},
        {"id": 2, "text": "Welcome to the lesson", "start": 3.5, "end": 6.8, "duration": 3.3},
    ]
    output_path = str(tmp_path / "test.srt")
    result = generate_srt(segments, output_path, text_field="text")

    assert os.path.exists(result)
    content = open(result, encoding="utf-8").read()
    assert "1\n00:00:00,500 --> 00:00:03,200\nHello everyone" in content
    assert "2\n00:00:03,500 --> 00:00:06,800\nWelcome to the lesson" in content


def test_generate_srt_japanese_text(tmp_path):
    segments = [
        {
            "id": 1,
            "text": "Hello",
            "text_jp": "こんにちは",
            "start": 0.0,
            "end": 2.0,
            "duration": 2.0,
        },
    ]
    output_path = str(tmp_path / "test_jp.srt")
    result = generate_srt(segments, output_path, text_field="text_jp")

    content = open(result, encoding="utf-8").read()
    assert "こんにちは" in content


def test_generate_srt_empty_segments(tmp_path):
    output_path = str(tmp_path / "empty.srt")
    result = generate_srt([], output_path, text_field="text")
    content = open(result, encoding="utf-8").read()
    assert content.strip() == ""
