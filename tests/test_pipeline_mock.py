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


@pytest.mark.asyncio
async def test_run_pipeline_restores_camera_labels_from_agent1(
    monkeypatch,
    synthetic_image_bytes,
):
    agent1_output = {
        "bestekposten": [
            {
                "nummer": "T2.22.11.3a",
                "image_indices": [1, 2],
                "camera_labels": ["Camera 1"],
                "observaties": ["Poutres visibles"],
                "zekerheid": "hoog",
                "toelichting": None,
            }
        ],
        "globale_opmerkingen": None,
    }
    agent2_output = {
        "bestekposten": [
            {
                "nummer": "T2.22.11.3a",
                "titel": "Poutres préfabriquées en béton armé",
                "image_indices": [1, 2],
                "camera_labels": [],
                "zekerheid": "hoog",
            }
        ],
        "aandachtspunten_globaal": [],
        "extra_input_nodig": [],
    }

    async def fake_agent1(*args, **kwargs):
        return agent1_output, [], {}

    async def fake_agent2(*args, **kwargs):
        return agent2_output, [], {}

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
    result = await run_pipeline(camera_inputs, "testrefs", region="walloon")

    restored = result["agent2_json"]["bestekposten"][0]
    assert restored["camera_labels"] == ["Camera 1"]
    assert "**Caméras :** Camera 1" in result["markdown_report"]
    assert "Inconnu" not in result["markdown_report"]
