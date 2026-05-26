from app.logging_utils import format_duration_mmss, format_timings_display


def test_format_duration_mmss_zero():
    assert format_duration_mmss(0) == "0:00"


def test_format_duration_mmss_seconds():
    assert format_duration_mmss(5.2) == "0:05"


def test_format_duration_mmss_minutes():
    assert format_duration_mmss(65.3) == "1:05"


def test_format_duration_mmss_long():
    assert format_duration_mmss(3661) == "61:01"


def test_format_timings_display():
    display = format_timings_display({"agent1": 12.4, "total": 65.0})
    assert display == {"agent1": "0:12", "total": "1:05"}
