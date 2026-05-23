"""Resize and compress uploaded images before sending to the vision model."""

from __future__ import annotations

import base64
import io
import logging
import os
from typing import Any

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "max_dim": 2048,
    "quality": 85,
    "agg_max_dim": 1280,
    "agg_quality": 70,
    "agg_trigger_mb": 8,
}

MIN_QUALITY_FLOOR = 40
QUALITY_STEP = 5

_warned: set[str] = set()
_cfg_cache: dict | None = None


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg)


def _parse_int_env(
    name: str,
    default: int,
    *,
    min_val: int | None = None,
    max_val: int | None = None,
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
    if max_val is not None and value > max_val:
        _warn_once(
            name,
            f"{name}={value} exceeds maximum {max_val}; using default {default}",
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


def _cfg() -> dict:
    global _cfg_cache
    if _cfg_cache is None:
        _cfg_cache = {
            "max_dim": _parse_int_env(
                "IMAGE_MAX_DIMENSION", _DEFAULTS["max_dim"], min_val=1
            ),
            "quality": _parse_int_env(
                "IMAGE_JPEG_QUALITY",
                _DEFAULTS["quality"],
                min_val=1,
                max_val=95,
            ),
            "agg_max_dim": _parse_int_env(
                "IMAGE_AGGRESSIVE_MAX_DIMENSION",
                _DEFAULTS["agg_max_dim"],
                min_val=1,
            ),
            "agg_quality": _parse_int_env(
                "IMAGE_AGGRESSIVE_JPEG_QUALITY",
                _DEFAULTS["agg_quality"],
                min_val=1,
                max_val=95,
            ),
            "agg_trigger_mb": _parse_float_env(
                "IMAGE_AGGRESSIVE_TRIGGER_MB",
                _DEFAULTS["agg_trigger_mb"],
                min_val=0,
            ),
        }
    return _cfg_cache


def _resolve_request_overrides(
    compression_options: dict[str, Any] | None,
) -> tuple[int | None, float | None, str]:
    if not compression_options:
        return None, None, "default"

    mode = compression_options.get("mode", "default")
    quality = compression_options.get("quality")
    target_image_mb = compression_options.get("target_image_mb")

    if mode == "advanced":
        return quality, target_image_mb, "advanced"
    if mode == "preset":
        preset = compression_options.get("preset", "medium")
        return quality, target_image_mb, f"preset:{preset}"
    return None, None, "default"


def _encode_jpeg(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def optimize_image(
    image_bytes: bytes,
    max_dim: int | None = None,
    quality: int | None = None,
    *,
    target_image_mb: float | None = None,
    compression_options: dict[str, Any] | None = None,
) -> tuple[bytes, str, dict[str, Any]]:
    """Return (compressed_jpeg_bytes, 'WxH' string, metadata dict)."""
    cfg = _cfg()
    tier = "standard"
    input_bytes = len(image_bytes)

    req_quality, req_target_mb, req_mode = _resolve_request_overrides(compression_options)
    if quality is None and req_quality is not None:
        quality = req_quality
    if target_image_mb is None and req_target_mb is not None:
        target_image_mb = req_target_mb

    if (
        max_dim is None
        and quality is None
        and input_bytes >= cfg["agg_trigger_mb"] * 1024 * 1024
    ):
        max_dim, quality = cfg["agg_max_dim"], cfg["agg_quality"]
        tier = "aggressive"

    if max_dim is None:
        max_dim = cfg["max_dim"]
    if quality is None:
        quality = cfg["quality"]

    if req_mode != "default":
        tier = req_mode

    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    encoded = _encode_jpeg(img, quality)
    target_bytes = (
        int(target_image_mb * 1024 * 1024) if target_image_mb is not None else None
    )
    if target_bytes is not None:
        while len(encoded) > target_bytes and quality > MIN_QUALITY_FLOOR:
            quality = max(MIN_QUALITY_FLOOR, quality - QUALITY_STEP)
            encoded = _encode_jpeg(img, quality)

    size_str = f"{img.size[0]}x{img.size[1]}"
    meta = {
        "tier": tier,
        "mode": req_mode,
        "input_bytes": input_bytes,
        "output_bytes": len(encoded),
        "dimensions": size_str,
        "max_dim": max_dim,
        "quality": quality,
        "target_image_mb": target_image_mb,
        "target_met": target_bytes is None or len(encoded) <= target_bytes,
    }

    logger.debug(
        "Image optimization tier=%s input_bytes=%d output_bytes=%d output=%s "
        "max_dim=%d quality=%d target_image_mb=%s",
        tier,
        input_bytes,
        len(encoded),
        size_str,
        max_dim,
        quality,
        target_image_mb,
    )

    return encoded, size_str, meta


def optimize_and_encode(
    image_bytes: bytes,
    compression_options: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Optimize then return (data-url, 'WxH', metadata)."""
    optimized, size_str, meta = optimize_image(
        image_bytes,
        compression_options=compression_options,
    )
    b64 = base64.b64encode(optimized).decode()
    return f"data:image/jpeg;base64,{b64}", size_str, meta
