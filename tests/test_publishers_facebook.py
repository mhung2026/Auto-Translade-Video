"""Tests for Facebook upload — all HTTP calls mocked."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def work_dir(tmp_path):
    (tmp_path / "youtube_metadata.json").write_text(
        (FIXTURES / "youtube_metadata.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    video = tmp_path / "dubbed_video.mp4"
    video.write_bytes(b"\x00" * 10_000)
    return tmp_path


@pytest.fixture
def fake_cfg():
    from src.publishers.auth import FacebookConfig
    return FacebookConfig(page_id="999", page_token="EAAB_fake")


def _post_responses(start_resp, transfer_resp, finish_resp):
    """Build a side_effect list for requests.post: start → transfer chunks → finish."""
    def make(json_payload, status=200):
        m = MagicMock()
        m.status_code = status
        m.json.return_value = json_payload
        m.raise_for_status = MagicMock()
        return m
    # one transfer call in our mock; production code may make many
    return [make(start_resp), make(transfer_resp), make(finish_resp)]


def test_upload_happy_path_returns_video_url(work_dir, fake_cfg):
    from src.publishers import facebook as fb

    responses = _post_responses(
        start_resp={"upload_session_id": "SESS_1", "video_id": "V_1",
                    "start_offset": "0", "end_offset": "10000"},
        transfer_resp={"start_offset": "10000", "end_offset": "10000"},
        finish_resp={"success": True, "video_id": "V_1"},
    )

    with patch.object(fb.auth, "load_facebook_config", return_value=fake_cfg), \
         patch.object(fb.requests, "post", side_effect=responses) as mock_post:
        result = fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is True
    assert result.platform == "facebook"
    assert result.video_id == "V_1"
    assert "facebook.com" in result.url

    finish_call = mock_post.call_args_list[-1]
    finish_data = finish_call.kwargs["data"]
    assert finish_data["upload_phase"] == "finish"
    assert finish_data["published"] is False
    assert finish_data["unpublished_content_type"] == "DRAFT"


def test_upload_public_publishes_immediately(work_dir, fake_cfg):
    from src.publishers import facebook as fb

    responses = _post_responses(
        start_resp={"upload_session_id": "S", "video_id": "V",
                    "start_offset": "0", "end_offset": "10000"},
        transfer_resp={"start_offset": "10000", "end_offset": "10000"},
        finish_resp={"success": True, "video_id": "V"},
    )
    with patch.object(fb.auth, "load_facebook_config", return_value=fake_cfg), \
         patch.object(fb.requests, "post", side_effect=responses) as mock_post:
        fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=True)

    finish_data = mock_post.call_args_list[-1].kwargs["data"]
    assert finish_data["published"] is True
    assert "unpublished_content_type" not in finish_data


def test_upload_token_expired_returns_actionable_error(work_dir, fake_cfg):
    from src.publishers import facebook as fb

    err_resp = MagicMock()
    err_resp.status_code = 400
    err_resp.json.return_value = {"error": {"code": 190, "message": "Invalid OAuth token"}}
    err_resp.raise_for_status = MagicMock()

    with patch.object(fb.auth, "load_facebook_config", return_value=fake_cfg), \
         patch.object(fb.requests, "post", return_value=err_resp):
        result = fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)

    assert result.success is False
    assert result.error == "auth_expired"
    assert "setup" in result.error_message.lower()


def test_upload_not_logged_in_returns_failure(work_dir):
    from src.publishers import facebook as fb
    from src.publishers.auth import NotLoggedInError

    with patch.object(fb.auth, "load_facebook_config", side_effect=NotLoggedInError("no cfg")):
        result = fb.upload(str(work_dir), str(work_dir / "dubbed_video.mp4"), public=False)
    assert result.success is False
    assert result.error == "auth_not_logged_in"
