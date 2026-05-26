import io
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.progress import progress_store


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_progress_jobs():
    with progress_store._lock:
        progress_store._jobs.clear()
    yield
    with progress_store._lock:
        progress_store._jobs.clear()


def test_progress_not_found(client):
    response = client.get("/progress/does-not-exist")
    assert response.status_code == 404


def test_progress_report_jobs_happy_path(
    client,
    monkeypatch,
    synthetic_image_bytes,
    fake_agent1_output,
    fake_agent2_output,
):
    async def fake_agent1(*args, **kwargs):
        return fake_agent1_output, [], {}

    async def fake_agent2(*args, **kwargs):
        return fake_agent2_output, [], {}

    monkeypatch.setattr("app.orchestrator.run_agent1", fake_agent1)
    monkeypatch.setattr("app.orchestrator.run_agent2", fake_agent2)
    monkeypatch.setattr("app.orchestrator.RequestLogger.persist", lambda self: None)
    monkeypatch.setattr("app.api.save_report_output", lambda *args, **kwargs: "outputs/test")

    files = [
        ("before_images", ("a.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("b.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
    ]
    response = client.post(
        "/progress-report/jobs",
        files=files,
        data={"region": "flemish", "camera_labels": '["Cam 1"]'},
    )
    assert response.status_code == 202
    request_id = response.json()["request_id"]

    deadline = time.time() + 5
    final = None
    while time.time() < deadline:
        progress = client.get(f"/progress/{request_id}")
        assert progress.status_code == 200
        payload = progress.json()
        if payload["status"] == "complete":
            final = payload
            break
        if payload["status"] == "error":
            pytest.fail(payload.get("error"))
        time.sleep(0.05)

    assert final is not None
    assert final["result"]["markdown_report"]
    assert final["result"]["timings_display"]


def test_progress_report_jobs_rejects_concurrent(
    client,
    monkeypatch,
    synthetic_image_bytes,
):
    progress_store.create_job("busy-job")
    progress_store.set_status("busy-job", "running")

    files = [
        ("before_images", ("a.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("b.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
    ]
    response = client.post(
        "/progress-report/jobs",
        files=files,
        data={"region": "flemish", "camera_labels": '["Cam 2"]', "track_order": '["pair"]'},
    )
    assert response.status_code == 409


def test_sync_progress_report_still_works(
    client,
    monkeypatch,
    synthetic_image_bytes,
    fake_agent1_output,
    fake_agent2_output,
):
    async def fake_agent1(*args, **kwargs):
        return fake_agent1_output, [], {}

    async def fake_agent2(*args, **kwargs):
        return fake_agent2_output, [], {}

    monkeypatch.setattr("app.orchestrator.run_agent1", fake_agent1)
    monkeypatch.setattr("app.orchestrator.run_agent2", fake_agent2)
    monkeypatch.setattr("app.orchestrator.RequestLogger.persist", lambda self: None)
    monkeypatch.setattr("app.api.save_report_output", lambda *args, **kwargs: "outputs/test")

    files = [
        ("before_images", ("a.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("b.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
    ]
    response = client.post(
        "/progress-report",
        files=files,
        data={"region": "flemish", "camera_labels": '["Cam 1"]'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["timings_display"]
    assert data["request_id"]
