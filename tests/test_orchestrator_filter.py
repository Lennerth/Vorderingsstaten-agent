from app.orchestrator import (
    InvalidBestekpostFilter,
    _bestekpost_matches_filter,
    _parse_bestekpost_filters,
    _parse_bestekpost_number,
    _parse_bestekpost_prefix,
)


def test_parse_exact_prefix():
    assert _parse_bestekpost_prefix("05.82") == (5, 82)


def test_parse_range_filter():
    parsed = _parse_bestekpost_filters(["05.82-05.89"])
    assert parsed[0]["type"] == "range"
    assert parsed[0]["start"] == (5, 82)
    assert parsed[0]["end"] == (5, 89)


def test_malformed_filter_raises():
    try:
        _parse_bestekpost_prefix("abc")
    except InvalidBestekpostFilter:
        pass
    else:
        raise AssertionError("expected InvalidBestekpostFilter")


def test_mixed_depth_range_raises():
    try:
        _parse_bestekpost_filters(["05-05.82"])
    except InvalidBestekpostFilter:
        pass
    else:
        raise AssertionError("expected InvalidBestekpostFilter")


def test_reversed_range_raises():
    try:
        _parse_bestekpost_filters(["05.89-05.82"])
    except InvalidBestekpostFilter:
        pass
    else:
        raise AssertionError("expected InvalidBestekpostFilter")


def test_bestekpost_matches_exact_and_range():
    parsed = _parse_bestekpost_filters(["05", "05.82-05.89"])
    assert _bestekpost_matches_filter("05.82", parsed)
    assert _bestekpost_matches_filter("05.89", parsed)
    assert not _bestekpost_matches_filter("06.01", parsed)


def test_parse_bestekpost_number_invalid():
    assert _parse_bestekpost_number("bad") == ()
