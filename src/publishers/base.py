"""Shared types and utilities for publishers."""
from dataclasses import dataclass


@dataclass
class PublishResult:
    """Outcome of a single platform upload attempt."""
    platform: str
    success: bool
    video_id: str | None = None
    url: str | None = None
    error: str | None = None
    error_message: str | None = None
    retryable: bool = False


def redact(token: str) -> str:
    """Return a safe-to-log version of a token: first 8 chars + ellipsis."""
    return token[:8] + "..."
