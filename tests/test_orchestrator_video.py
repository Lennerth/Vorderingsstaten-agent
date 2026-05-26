import pytest

from app.kb import run_agent1
from app.orchestrator import run_pipeline


@pytest.mark.asyncio
async def test_mixed_camera_inputs_image_numbering(
    monkeypatch,
    fake_agent1_output,
    fake_agent2_output,
    synthetic_image_bytes,
):
    captured_images = []

    async def fake_agent1(images, *args, **kwargs):
        captured_images.extend(images)
        return fake_agent1_output, [], {}

    async def fake_agent2(*args, **kwargs):
        return fake_agent2_output, [], {}

    monkeypatch.setattr("app.orchestrator.run_agent1", fake_agent1)
    monkeypatch.setattr("app.orchestrator.run_agent2", fake_agent2)
    monkeypatch.setattr("app.orchestrator.RequestLogger.persist", lambda self: None)

    camera_inputs = [
        {
            "kind": "pair",
            "camera_label": "Cam Pair",
            "before_bytes": synthetic_image_bytes,
            "after_bytes": synthetic_image_bytes,
        },
        {
            "kind": "timelapse",
            "camera_label": "Cam TL",
            "frames": [
                {"timestamp_s": 0.0, "jpeg_bytes": synthetic_image_bytes[:100000]},
                {"timestamp_s": 5.0, "jpeg_bytes": synthetic_image_bytes[:100000]},
            ],
        },
    ]
    await run_pipeline(camera_inputs, "mix001", region="flemish")
    indices = [item[0] for item in captured_images]
    assert indices == list(range(1, len(indices) + 1))
    roles = [item[2] for item in captured_images]
    assert roles[:2] == ["voor", "na"]
    assert roles[2].startswith("t=")
