import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.utils import video_processing
from app.utils.video_processing import (
    compute_sample_timestamps,
    extract_frames,
    get_video_limits,
    validate_frame_count,
    validate_video_upload,
    validate_video_metadata,
)


def test_compute_sample_timestamps_endpoints():
    ts = compute_sample_timestamps(60.0, 4)
    assert ts[0] == 0.0
    assert ts[-1] < 60.0
    assert len(ts) == 4


def test_compute_sample_timestamps_uses_frame_metadata():
    ts = compute_sample_timestamps(60.0, 8, frame_count=1800, fps=30.0)
    last_frame_t = round((1800 - 1) / 30.0, 3)
    assert ts[0] == 0.0
    assert ts[-1] < 60.0
    assert ts[-1] <= last_frame_t
    assert len(ts) == 8


def test_compute_sample_timestamps_caps_to_frame_count():
    ts = compute_sample_timestamps(10.0, 8, frame_count=3, fps=1.0)
    assert len(ts) == 3


def test_extract_frame_retries_earlier_timestamp(monkeypatch):
    calls: list[float] = []

    def fake_run(path: str, timestamp_s: float):
        calls.append(timestamp_s)
        result = MagicMock()
        if timestamp_s >= 59.94:
            result.returncode = 1
            result.stdout = b""
            result.stderr = b"seek failed"
            return result
        result.returncode = 0
        result.stdout = b"fake-png"
        result.stderr = b""
        return result

    monkeypatch.setattr(video_processing, "_run_ffmpeg_extract", fake_run)
    png_bytes, actual_t = video_processing._extract_frame_png_at(
        "clip.mp4",
        59.94,
        frame_interval=1 / 30,
    )
    assert png_bytes == b"fake-png"
    assert actual_t < 59.94
    assert 59.94 in calls


def test_validate_video_upload_accepts_mp4():
    validate_video_upload("clip.mp4", "video/mp4", 1024)


def test_validate_video_upload_rejects_bad_mime():
    with pytest.raises(ValueError, match="MIME"):
        validate_video_upload("clip.avi", "video/x-msvideo", 1024)


def test_extract_frames_from_synthetic_video(synthetic_video_bytes):
    frames = extract_frames(synthetic_video_bytes, max_frames=4)
    assert len(frames) == 4
    timestamps = [frame.timestamp_s for frame in frames]
    assert timestamps[0] == 0.0
    assert timestamps == sorted(timestamps)
    for frame in frames:
        Image.open(io.BytesIO(frame.jpeg_bytes)).verify()


def test_validate_video_metadata_rejects_long_duration():
    with pytest.raises(ValueError, match="duration"):
        validate_video_metadata({"duration_s": 9999, "frame_count": 100})


def test_validate_frame_count_within_limits():
    limits = get_video_limits()
    assert validate_frame_count(limits.default_frames) == limits.default_frames
    assert validate_frame_count(limits.max_frames) == limits.max_frames


def test_validate_frame_count_rejects_too_low():
    with pytest.raises(ValueError, match="at least 2"):
        validate_frame_count(1)


def test_validate_frame_count_rejects_too_high():
    limits = get_video_limits()
    with pytest.raises(ValueError, match="maximum"):
        validate_frame_count(limits.max_frames + 1)
