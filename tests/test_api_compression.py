import pytest
from fastapi import HTTPException

from app.api import parse_compression_options


def test_compression_preset_medium():
    opts = parse_compression_options(compression_preset="medium")
    assert opts["mode"] == "default"


def test_compression_preset_high():
    opts = parse_compression_options(compression_preset="high")
    assert opts["mode"] == "preset"
    assert opts["quality"] == 65


def test_compression_advanced_valid():
    opts = parse_compression_options(
        compression_advanced="true",
        jpeg_quality="80",
        target_image_mb="2",
    )
    assert opts["mode"] == "advanced"
    assert opts["quality"] == 80


def test_compression_unknown_preset():
    with pytest.raises(HTTPException):
        parse_compression_options(compression_preset="invalid")
