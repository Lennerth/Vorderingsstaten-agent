import pytest

from app.regions import KB_MESSAGES, OUTPUT_STORAGE_LABELS, REPORT_LABELS, normalize_region


def test_region_label_key_parity():
    for mapping in (KB_MESSAGES, REPORT_LABELS, OUTPUT_STORAGE_LABELS):
        flemish_keys = set(mapping["flemish"].keys())
        walloon_keys = set(mapping["walloon"].keys())
        assert flemish_keys == walloon_keys


def test_normalize_region():
    assert normalize_region(" Flemish ") == "flemish"
    with pytest.raises(ValueError):
        normalize_region("invalid")
