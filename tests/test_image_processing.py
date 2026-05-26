import os

from app.utils.image_processing import MIN_QUALITY_FLOOR, optimize_image


def test_optimize_image_resizes_large_input(synthetic_image_bytes):
    out, size_str, meta = optimize_image(synthetic_image_bytes)
    assert out.startswith(b"\xff\xd8")
    w, h = map(int, size_str.split("x"))
    assert max(w, h) <= 2048
    assert meta["tier"] == "standard"


def test_optimize_image_target_step_down(rgba_image_bytes, monkeypatch):
    monkeypatch.setenv("IMAGE_JPEG_QUALITY", "85")
    out, _, meta = optimize_image(
        rgba_image_bytes,
        target_image_mb=0.0001,
    )
    assert len(out) > 0
    assert meta["quality"] >= MIN_QUALITY_FLOOR


def test_optimize_image_aggressive_tier(monkeypatch, synthetic_image_bytes):
    import app.utils.image_processing as ip

    monkeypatch.setenv("IMAGE_AGGRESSIVE_TRIGGER_MB", "0")
    ip._cfg_cache = None
    _, _, meta = optimize_image(synthetic_image_bytes)
    assert meta["tier"] == "aggressive"
