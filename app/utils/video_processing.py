"""Video preprocessing for timelapse uploads: probe, validate, extract frames."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

from app.utils.image_processing import optimize_image

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


@dataclass(frozen=True)
class ExtractedFrame:
    timestamp_s: float
    jpeg_bytes: bytes


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
    """Validate MIME type, extension, and byte size before decoding."""
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


def validate_video_metadata(probe_info: dict) -> None:
    """Enforce duration and frame-count limits after probing."""
    limits = get_video_limits()
    duration_s = float(probe_info.get("duration_s") or 0)
    frame_count = int(probe_info.get("frame_count") or 0)

    if duration_s <= 0:
        raise ValueError("Could not determine video duration.")

    if duration_s > limits.max_duration_s:
        raise ValueError(
            f"Video duration {duration_s:.1f}s exceeds max of {limits.max_duration_s}s."
        )

    if frame_count <= 0:
        raise ValueError("Could not determine video frame count.")

    if frame_count < 2 and limits.max_frames > 1:
        raise ValueError(
            f"Video has only {frame_count} frame(s); at least 2 are required for timelapse."
        )


def probe_video(video_bytes: bytes) -> dict:
    """Return duration, fps, dimensions, frame count, and codec for a video blob."""
    with _video_tempfile(video_bytes) as path:
        try:
            frame_count, duration_s = imageio_ffmpeg.count_frames_and_secs(path)
        except Exception as exc:
            raise ValueError(f"Failed to probe video: {exc}") from exc

        width, height, codec = _probe_stream_info(path)
        fps = frame_count / duration_s if duration_s > 0 else 0.0

        return {
            "duration_s": round(duration_s, 3),
            "fps": round(fps, 3),
            "width": width,
            "height": height,
            "frame_count": int(frame_count),
            "codec": codec,
        }


def compute_sample_timestamps(
    duration_s: float,
    count: int,
    *,
    frame_count: int | None = None,
    fps: float | None = None,
) -> list[float]:
    """First + last + uniformly spaced timestamps (inclusive endpoints).

    Uses frame_count and fps when available to avoid sampling at or beyond the
    last decodable frame, which often sits slightly before metadata duration.
    """
    if count <= 0:
        return []
    if count == 1:
        return [0.0]
    if duration_s <= 0:
        return [0.0] * count

    if frame_count is not None and frame_count > 0:
        count = min(count, frame_count)

    frame_interval: float | None = None
    if fps and fps > 0:
        frame_interval = 1.0 / fps
    elif frame_count and frame_count > 1:
        frame_interval = duration_s / (frame_count - 1)

    if frame_count and frame_count > 1 and fps and fps > 0:
        last_frame_t = (frame_count - 1) / fps
        margin = frame_interval or 0.033
        safe_end = min(last_frame_t, duration_s - margin)
    elif frame_interval:
        safe_end = max(duration_s - frame_interval, frame_interval)
    else:
        safe_end = duration_s * 0.99

    safe_end = max(safe_end, 0.0)
    if safe_end <= 0:
        return [0.0] * count

    step = safe_end / (count - 1)
    timestamps = [round(i * step, 3) for i in range(count)]
    timestamps[0] = 0.0
    timestamps[-1] = round(safe_end, 3)
    return timestamps


def extract_frames(
    video_bytes: bytes,
    *,
    max_frames: int | None = None,
) -> list[ExtractedFrame]:
    """Extract representative JPEG frames: first, last, and uniform spacing."""
    limits = get_video_limits()
    n_frames = max_frames if max_frames is not None else limits.max_frames
    n_frames = min(n_frames, limits.max_frames)

    probe = probe_video(video_bytes)
    validate_video_metadata(probe)

    frame_count = int(probe["frame_count"])
    n_frames = min(n_frames, frame_count)
    fps = float(probe.get("fps") or 0)

    timestamps = compute_sample_timestamps(
        probe["duration_s"],
        n_frames,
        frame_count=frame_count,
        fps=fps,
    )
    extracted: list[ExtractedFrame] = []

    if fps > 0:
        frame_interval = 1.0 / fps
    elif frame_count > 1:
        frame_interval = probe["duration_s"] / (frame_count - 1)
    else:
        frame_interval = 0.033

    with _video_tempfile(video_bytes) as path:
        for timestamp_s in timestamps:
            png_bytes, actual_t = _extract_frame_png_at(
                path,
                timestamp_s,
                frame_interval=frame_interval,
            )
            jpeg_bytes, _, _ = optimize_image(png_bytes)
            extracted.append(
                ExtractedFrame(timestamp_s=actual_t, jpeg_bytes=jpeg_bytes)
            )

    logger.info(
        "Extracted %d frames from video (duration=%.1fs, targets=%s, actual=%s)",
        len(extracted),
        probe["duration_s"],
        timestamps,
        [frame.timestamp_s for frame in extracted],
    )
    return extracted


@contextmanager
def _video_tempfile(video_bytes: bytes):
    suffix = ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    path = tmp.name
    try:
        tmp.write(video_bytes)
        tmp.flush()
        tmp.close()
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _probe_stream_info(path: str) -> tuple[int, int, str]:
    """Best-effort width/height/codec via ffmpeg stderr parse."""
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-i",
        path,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    stderr = result.stderr or ""
    width, height, codec = 0, 0, "unknown"

    for line in stderr.splitlines():
        if "Video:" in line:
            parts = line.split("Video:", 1)[1].strip().split(",")
            if parts:
                codec = parts[0].strip().split()[0]
            for token in parts:
                token = token.strip()
                if "x" in token and token[0].isdigit():
                    wh = token.split()[0]
                    if "x" in wh:
                        w_str, h_str = wh.split("x", 1)
                        try:
                            width = int(w_str)
                            height = int(h_str)
                        except ValueError:
                            pass
                    break
            break

    return width, height, codec


def _retry_timestamps(target_s: float, frame_interval: float) -> list[float]:
    """Candidate seek times: target, then slightly earlier on failure."""
    offsets = [0.0, frame_interval, 0.25, 0.5]
    candidates: list[float] = []
    seen: set[float] = set()
    for offset in offsets:
        candidate = round(max(0.0, target_s - offset), 3)
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def _run_ffmpeg_extract(path: str, timestamp_s: float) -> subprocess.CompletedProcess[bytes]:
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, timestamp_s):.3f}",
        "-i",
        path,
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    return subprocess.run(cmd, capture_output=True, check=False)


def _extract_frame_png_at(
    path: str,
    timestamp_s: float,
    *,
    frame_interval: float = 0.033,
) -> tuple[bytes, float]:
    """Extract a PNG frame, retrying slightly earlier on seek failures."""
    last_error = ""
    for candidate in _retry_timestamps(timestamp_s, frame_interval):
        result = _run_ffmpeg_extract(path, candidate)
        if result.returncode == 0 and result.stdout:
            if candidate != timestamp_s:
                logger.debug(
                    "Extracted frame at t=%.3fs after retry (target was t=%.3fs)",
                    candidate,
                    timestamp_s,
                )
            return result.stdout, candidate
        last_error = (result.stderr or b"").decode(errors="replace").strip()

    raise ValueError(
        f"Failed to extract frame at t={timestamp_s}s: {last_error or 'unknown ffmpeg error'}"
    )
