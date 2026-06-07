"""Tests for YouTube upload module — all API calls mocked."""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def work_dir(tmp_path):
    """A minimal work_dir with metadata + fake video file."""
    (tmp_path / "youtube_metadata.json").write_text(
        (FIXTURES / "youtube_metadata.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "dubbed_video.mp4").write_bytes(b"fake_mp4_bytes")
    return tmp_path


def _mock_youtube_service(video_id="VID_abc123"):
    """Build a mock youtube service whose insert().execute() returns video_id."""
    service = MagicMock()
    insert_request = MagicMock()
    insert_request.next_chunk.side_effect = [
        (None, None),                                       # progress, no response
        (None, {"id": video_id}),                           # final chunk, got response
    ]
    service.videos.return_value.insert.return_value = insert_request
    service.thumbnails.return_value.set.return_value.execute.return_value = {}
    service.captions.return_value.insert.return_value.execute.return_value = {"id": "CAP_x"}
    return service


def test_upload_happy_path_returns_video_url(work_dir):
    from src.publishers import youtube as yt

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        mock_build.return_value = _mock_youtube_service(video_id="VID_abc123")

        result = yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is True
    assert result.platform == "youtube"
    assert result.video_id == "VID_abc123"
    assert result.url == "https://youtube.com/watch?v=VID_abc123"


def test_upload_truncates_title_to_100_chars(work_dir):
    from src.publishers import youtube as yt

    long_title = "A" * 200
    meta_path = work_dir / "youtube_metadata.json"
    meta_path.write_text(json.dumps({"title": long_title, "description": "", "hashtags": []}), encoding="utf-8")

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = _mock_youtube_service()
        mock_build.return_value = service
        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

        # Inspect the body passed to insert()
        call_kwargs = service.videos.return_value.insert.call_args.kwargs
        assert len(call_kwargs["body"]["snippet"]["title"]) == 100


def test_upload_public_flag_sets_privacy_status(work_dir):
    from src.publishers import youtube as yt

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        # Public upload
        service = _mock_youtube_service()
        mock_build.return_value = service
        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=True)
        body = service.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "public"

        # Private upload — rebuild service so next_chunk side_effect is fresh
        service = _mock_youtube_service()
        mock_build.return_value = service
        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)
        body = service.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "private"


def test_upload_caps_tags_at_30(work_dir):
    from src.publishers import youtube as yt

    many_tags = [f"#tag{i}" for i in range(60)]
    meta_path = work_dir / "youtube_metadata.json"
    meta_path.write_text(json.dumps({"title": "t", "description": "d", "hashtags": many_tags}), encoding="utf-8")

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = _mock_youtube_service()
        mock_build.return_value = service
        yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

        body = service.videos.return_value.insert.call_args.kwargs["body"]
        assert len(body["snippet"]["tags"]) == 30


def test_upload_quota_exceeded_returns_retryable_error(work_dir):
    from googleapiclient.errors import HttpError
    from src.publishers import youtube as yt

    quota_error = HttpError(
        resp=MagicMock(status=403, reason="quotaExceeded"),
        content=b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}',
    )

    with patch.object(yt, "_build_service") as mock_build, \
         patch.object(yt.auth, "load_youtube_credentials", return_value=MagicMock()):
        service = MagicMock()
        service.videos.return_value.insert.return_value.next_chunk.side_effect = quota_error
        mock_build.return_value = service

        result = yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is False
    assert result.error == "quota_exceeded"
    assert result.retryable is True


def test_upload_not_logged_in_returns_failure(work_dir):
    from src.publishers import youtube as yt
    from src.publishers.auth import NotLoggedInError

    with patch.object(yt.auth, "load_youtube_credentials", side_effect=NotLoggedInError("no token")):
        result = yt.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is False
    assert result.error == "auth_not_logged_in"
    assert result.retryable is False
