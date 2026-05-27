import logging

from fastapi.testclient import TestClient

import app.main as main
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


def test_default_root_serves_v2_frontend_when_build_exists(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text("<!doctype html><div>V2 frontend marker</div>", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setattr(main, "FRONTEND_INDEX", index)

    client = TestClient(main.create_app("v2"))
    response = client.get("/")

    assert response.status_code == 200
    assert "V2 frontend marker" in response.text


def test_default_mode_exposes_classic_ui_at_classic():
    client = TestClient(main.create_app("v2"))
    response = client.get("/classic")

    assert response.status_code == 200
    assert "Vorderingsstaat Generator" in response.text


def test_old_frontend_mode_serves_classic_ui_at_root():
    client = TestClient(main.create_app("classic"))
    response = client.get("/")

    assert response.status_code == 200
    assert "Vorderingsstaat Generator" in response.text


def test_old_frontend_mode_still_exposes_v2_at_v2(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text("<!doctype html><div>V2 frontend marker</div>", encoding="utf-8")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setattr(main, "FRONTEND_INDEX", index)

    client = TestClient(main.create_app("classic"))
    response = client.get("/v2")

    assert response.status_code == 200
    assert "V2 frontend marker" in response.text


def test_v2_spa_fallback_serves_root_public_assets(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text("<!doctype html><div>V2 frontend marker</div>", encoding="utf-8")
    logo = dist / "buildwise-logo.png"
    logo.write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setattr(main, "FRONTEND_INDEX", index)

    client = TestClient(main.create_app("v2"))
    response = client.get("/buildwise-logo.png")

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


def test_default_root_reports_missing_v2_build(tmp_path, monkeypatch):
    dist = tmp_path / "missing-dist"
    monkeypatch.setattr(main, "FRONTEND_DIST", dist)
    monkeypatch.setattr(main, "FRONTEND_INDEX", dist / "index.html")

    client = TestClient(main.create_app("v2"))
    response = client.get("/")

    assert response.status_code == 503
    assert "npm run build" in response.text
