import pytest

from app.orchestrator import run_pipeline


@pytest.mark.asyncio
async def test_run_pipeline_with_mocked_agents(
    monkeypatch,
    fake_agent1_output,
    fake_agent2_output,
    synthetic_image_bytes,
):
    async def fake_agent1(*args, **kwargs):
        return fake_agent1_output, [], {"input_tokens": 1, "output_tokens": 1}

    async def fake_agent2(*args, **kwargs):
        return fake_agent2_output, [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr("app.orchestrator.run_agent1", fake_agent1)
    monkeypatch.setattr("app.orchestrator.run_agent2", fake_agent2)
    monkeypatch.setattr("app.orchestrator.RequestLogger.persist", lambda self: None)

    camera_inputs = [
        {
            "kind": "pair",
            "camera_label": "Camera 1",
            "before_bytes": synthetic_image_bytes,
            "after_bytes": synthetic_image_bytes,
        }
    ]
    result = await run_pipeline(camera_inputs, "test123", region="flemish")
    assert "markdown_report" in result
    assert result["agent2_json"]["bestekposten"]
    assert "evidence" in result
    assert "extracted_frames" in result
    assert any(
        LOW in (bp.get("open_punten") or [""])[0]
        for bp in result["agent2_json"]["bestekposten"]
        for LOW in ["Manuele check"]
    )
