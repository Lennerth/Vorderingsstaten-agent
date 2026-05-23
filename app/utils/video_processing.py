"""Video preprocessing scaffold for timelapse uploads (frame extraction lands in v1.8)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "max_duration_s": 120,
    "max_file_mb": 200,
    "max_frames": 8,
    "accepted_mime": "video/mp4,video/quicktime",
    "accepted_ext": ".mp4,.mov",
}

_warned: set[str] = set()
_limits_cache: VideoLimits | None = None


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg)


def _parse_int_env(
    name: str,
    default: int,
    *,
    min_val: int | None = None,
) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _warn_once(name, f"{name}={raw!r} is not a valid integer; using default {default}")
        return default
    if min_val is not None and value < min_val:
        _warn_once(
            name,
            f"{name}={value} is below minimum {min_val}; using default {default}",
        )
        return default
    return value


def _parse_float_env(
    name: str,
    default: float,
    *,
    min_val: float | None = None,
) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        _warn_once(name, f"{name}={raw!r} is not a valid number; using default {default}")
        return default
    if min_val is not None and value < min_val:
        _warn_once(
            name,
            f"{name}={value} is below minimum {min_val}; using default {default}",
        )
        return default
    return value


def _parse_csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        raw = default
    return tuple(item.strip().lower() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class VideoLimits:
    max_duration_s: int
    max_file_mb: int
    max_frames: int
    accepted_mime: tuple[str, ...]
    accepted_ext: tuple[str, ...]


def get_video_limits() -> VideoLimits:
    global _limits_cache
    if _limits_cache is None:
        _limits_cache = VideoLimits(
            max_duration_s=_parse_int_env(
                "VIDEO_MAX_DURATION_S",
                _DEFAULTS["max_duration_s"],
                min_val=1,
            ),
            max_file_mb=_parse_int_env(
                "VIDEO_MAX_FILE_MB",
                _DEFAULTS["max_file_mb"],
                min_val=1,
            ),
            max_frames=_parse_int_env(
                "VIDEO_MAX_FRAMES",
                _DEFAULTS["max_frames"],
                min_val=1,
            ),
            accepted_mime=_parse_csv_env(
                "VIDEO_ACCEPTED_MIME",
                _DEFAULTS["accepted_mime"],
            ),
            accepted_ext=_parse_csv_env(
                "VIDEO_ACCEPTED_EXT",
                _DEFAULTS["accepted_ext"],
            ),
        )
    return _limits_cache


def validate_video_upload(filename: str, content_type: str, size_bytes: int) -> None:
    """Validate a video upload against configured limits.

    Enforced in v1.7c: MIME type, file extension, and byte size.
    Not enforced until v1.8 (requires a real decoder): duration and frame count.
    """
    limits = get_video_limits()
    normalized_mime = (content_type or "").split(";")[0].strip().lower()
    extension = Path(filename or "").suffix.lower()

    if normalized_mime not in limits.accepted_mime:
        raise ValueError(
            f"Unsupported video MIME type {content_type!r}. "
            f"Accepted: {', '.join(limits.accepted_mime)}."
        )

    if extension not in limits.accepted_ext:
        raise ValueError(
            f"Unsupported video extension {extension!r}. "
            f"Accepted: {', '.join(limits.accepted_ext)}."
        )

    max_bytes = limits.max_file_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValueError(
            f"Video exceeds max size of {limits.max_file_mb} MB "
            f"({size_bytes} bytes uploaded)."
        )

    # TODO 1.8: enforce limits.max_duration_s and limits.max_frames once a decoder exists.


def extract_frames(video_bytes: bytes, *, max_frames: int | None = None) -> list[bytes]:
    """Extract representative frames from a video (not implemented until v1.8)."""
    raise NotImplementedError("Video frame extraction lands in v1.8")
