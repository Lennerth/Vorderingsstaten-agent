"""Resize and compress uploaded images before sending to the vision model."""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

MAX_DIMENSION = 2048
JPEG_QUALITY = 85


def optimize_image(
    image_bytes: bytes,
    max_dim: int = MAX_DIMENSION,
    quality: int = JPEG_QUALITY,
) -> tuple[bytes, str]:
    """Return (compressed_jpeg_bytes, 'WxH' string)."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_dim:
        ratio = max_dim / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), f"{img.size[0]}x{img.size[1]}"


def optimize_and_encode(image_bytes: bytes) -> tuple[str, str]:
    """Optimize then return (data-url, 'WxH')."""
    optimized, size_str = optimize_image(image_bytes)
    b64 = base64.b64encode(optimized).decode()
    return f"data:image/jpeg;base64,{b64}", size_str
