"""Publishers — upload dubbed videos to YouTube / Facebook / (future) TikTok.

Public entry point:

    from src.publishers import publish
    results = publish(work_dir, video_path, platforms=["youtube", "facebook"], public=False)
"""
import importlib
import logging

from src.publishers.base import PublishResult

logger = logging.getLogger(__name__)

REGISTRY = {
    "youtube": "src.publishers.youtube",
    "facebook": "src.publishers.facebook",
}


def publish(
    work_dir: str,
    video_path: str,
    platforms: list[str],
    public: bool = False,
) -> dict[str, PublishResult]:
    """Run `upload(work_dir, video_path, public)` on each platform sequentially.

    One platform failing does NOT block the others. Each platform's exception
    is caught and reflected as a failure PublishResult.
    """
    results: dict[str, PublishResult] = {}
    for platform in platforms:
        module_name = REGISTRY.get(platform)
        if module_name is None:
            results[platform] = PublishResult(
                platform=platform, success=False,
                error="unknown_platform",
                error_message=f"Unknown publisher: {platform}. Known: {sorted(REGISTRY)}",
            )
            continue
        try:
            module = importlib.import_module(module_name)
            results[platform] = module.upload(work_dir, video_path, public=public)
        except Exception as e:
            logger.exception(f"Publisher '{platform}' raised an exception")
            results[platform] = PublishResult(
                platform=platform, success=False,
                error="exception",
                error_message=f"{type(e).__name__}: {e}",
                retryable=False,
            )
    return results
