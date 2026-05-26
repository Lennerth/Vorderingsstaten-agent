import logging

from app.main import SuppressProgressPollFilter


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_progress_poll_access_log_is_suppressed():
    log_filter = SuppressProgressPollFilter()
    record = _record('127.0.0.1 - "GET /progress/abc123 HTTP/1.1" 200 OK')

    assert not log_filter.filter(record)


def test_other_access_logs_are_kept():
    log_filter = SuppressProgressPollFilter()
    record = _record('127.0.0.1 - "POST /progress-report/jobs HTTP/1.1" 202 Accepted')

    assert log_filter.filter(record)
