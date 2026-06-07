"""Regression tests for the new progress_callback kwarg on both pipelines."""


def test_notify_does_nothing_when_callback_none():
    from pipeline_vi import _notify
    _notify(None, "download", "running")
    _notify(None, "download", "ok", video_path="/tmp/x.mp4")


def test_notify_calls_callback_with_step_status_and_kwargs():
    from pipeline_vi import _notify
    captured = []

    def cb(step, status, **info):
        captured.append((step, status, info))

    _notify(cb, "asr", "ok", n_segments=5)
    assert captured == [("asr", "ok", {"n_segments": 5})]


def test_notify_swallows_callback_exceptions():
    """A bad callback must not crash the pipeline."""
    from pipeline_vi import _notify

    def bad_cb(step, status, **info):
        raise RuntimeError("boom")

    _notify(bad_cb, "asr", "ok")


def test_pipeline_signature_accepts_progress_callback_kwarg():
    import inspect
    from pipeline_vi import run_pipeline_vi
    sig = inspect.signature(run_pipeline_vi)
    assert "progress_callback" in sig.parameters
    assert sig.parameters["progress_callback"].default is None


def test_run_pipeline_signature_for_jp_also_has_callback():
    import inspect
    from pipeline import run_pipeline
    sig = inspect.signature(run_pipeline)
    assert "progress_callback" in sig.parameters
    assert sig.parameters["progress_callback"].default is None
