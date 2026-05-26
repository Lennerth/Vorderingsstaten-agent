import io

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_config_endpoint(client):
    response = client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert "max_cameras" in data
    assert data["video_default_frames"] >= 2
    assert data["video_max_frames"] >= data["video_default_frames"]


def test_progress_report_mismatched_counts(client, synthetic_image_bytes):
    files = [
        ("before_images", ("a.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("b.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("c.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
    ]
    response = client.post("/progress-report", files=files, data={"region": "flemish"})
    assert response.status_code == 400


def test_progress_report_invalid_region(client, synthetic_image_bytes):
    files = [
        ("before_images", ("a.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("b.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
    ]
    response = client.post(
        "/progress-report",
        files=files,
        data={"region": "invalid", "camera_labels": '["Cam 1"]'},
    )
    assert response.status_code == 400


def test_progress_report_invalid_compression(client, synthetic_image_bytes):
    files = [
        ("before_images", ("a.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
        ("after_images", ("b.jpg", io.BytesIO(synthetic_image_bytes), "image/jpeg")),
    ]
    response = client.post(
        "/progress-report",
        files=files,
        data={
            "region": "flemish",
            "camera_labels": '["Cam 1"]',
            "compression_preset": "invalid",
        },
    )
    assert response.status_code == 400
