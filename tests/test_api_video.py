import io

from fastapi.testclient import TestClient

from app.main import app


def test_video_upload_rejects_bad_mime(synthetic_video_bytes):
    client = TestClient(app)
    files = [
        ("videos", ("clip.avi", io.BytesIO(synthetic_video_bytes), "video/x-msvideo")),
    ]
    response = client.post(
        "/progress-report",
        files=files,
        data={
            "region": "flemish",
            "video_labels": '["Cam 1"]',
            "track_order": '["timelapse"]',
        },
    )
    assert response.status_code == 400


def test_video_upload_happy_path(monkeypatch, synthetic_video_bytes, fake_agent1_output, fake_agent2_output):
    async def fake_agent1(*args, **kwargs):
        return fake_agent1_output, [], {}

    async def fake_agent2(*args, **kwargs):
        return fake_agent2_output, [], {}

    monkeypatch.setattr("app.orchestrator.run_agent1", fake_agent1)
    monkeypatch.setattr("app.orchestrator.run_agent2", fake_agent2)
    monkeypatch.setattr("app.orchestrator.RequestLogger.persist", lambda self: None)

    client = TestClient(app)
    files = [
        ("videos", ("clip.mp4", io.BytesIO(synthetic_video_bytes), "video/mp4")),
    ]
    response = client.post(
        "/progress-report",
        files=files,
        data={
            "region": "flemish",
            "video_labels": '["Cam 1"]',
            "track_order": '["timelapse"]',
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("extracted_frames")
