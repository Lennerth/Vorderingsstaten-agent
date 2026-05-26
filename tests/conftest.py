"""Shared pytest fixtures."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def synthetic_image_bytes() -> bytes:
    img = Image.new("RGB", (4000, 3000), color=(120, 180, 90))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def exif_rotated_image_bytes() -> bytes:
    img = Image.new("RGB", (800, 600), color=(200, 50, 50))
    exif = ImageOps.ExifTags.Base.Orientation
    img = ImageOps.exif_transpose(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=img.getexif())
    return buf.getvalue()


@pytest.fixture
def rgba_image_bytes() -> bytes:
    img = Image.new("RGBA", (500, 400), color=(10, 20, 30, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def synthetic_video_bytes(tmp_path):
    """Create a short synthetic MP4 (~3s at 10fps)."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for i in range(30):
        color = (i * 8 % 255, 100, 200 - i * 5)
        img = Image.new("RGB", (320, 240), color=color)
        img.save(frames_dir / f"frame_{i:03d}.png")

    output_path = tmp_path / "test.mp4"
    cmd = [
        ffmpeg_exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        "10",
        "-i",
        str(frames_dir / "frame_%03d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path.read_bytes()


@pytest.fixture
def fake_agent1_output() -> dict:
    return {
        "bestekposten": [
            {
                "nummer": "02.81",
                "image_indices": [1, 2],
                "camera_labels": ["Camera 1"],
                "observaties": ["Werfcontainer geplaatst"],
                "zekerheid": "laag",
                "toelichting": "Tijdelijke werfinrichting zichtbaar.",
            }
        ],
        "globale_opmerkingen": None,
    }


@pytest.fixture
def fake_agent2_output() -> dict:
    return {
        "bestekposten": [
            {
                "nummer": "02.81",
                "titel": "Tijdelijke werfinrichting",
                "image_indices": [1, 2],
                "camera_labels": ["Camera 1"],
                "zekerheid": "laag",
                "zichtbaar_uitgevoerd": ["Container geplaatst"],
                "bestekeisen": ["Volgens bestek"],
                "bron": {
                    "deel": "0",
                    "sectie": "02.81",
                    "fragmenten": ["Fragment"],
                    "bestandsnaam": "Deel-0.docx",
                },
                "open_punten": [],
                "volgende_stap": "Controleer plaatsing",
            },
            {
                "nummer": "02.81",
                "titel": "Duplicaat",
                "image_indices": [2],
                "camera_labels": ["Camera 2"],
                "zekerheid": "laag",
                "zichtbaar_uitgevoerd": ["Extra"],
                "bestekeisen": ["Eis"],
                "bron": {
                    "deel": "0",
                    "sectie": "02.81",
                    "fragmenten": ["F"],
                    "bestandsnaam": "Deel-0.docx",
                },
                "open_punten": ["Check"],
                "volgende_stap": "Stap",
            },
        ],
        "aandachtspunten_globaal": [],
        "extra_input_nodig": [],
    }


@pytest.fixture
def tmp_outputs_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path / "outputs"
