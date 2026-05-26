from app.models import Agent1Bestekpost, Agent1Output, Agent2Output, BestekpostDetail
from app.orchestrator import _enforce_low_confidence, _merge_duplicates, _preserve_visual_references
from app.regions import LOW_CONFIDENCE_WARNING


def test_enforce_low_confidence_initializes_open_punten():
    agent1 = Agent1Output(
        bestekposten=[
            Agent1Bestekpost(
                nummer="02.81",
                image_indices=[1],
                camera_labels=["Cam 1"],
                observaties=["x"],
                zekerheid="laag",
                toelichting=None,
            )
        ]
    )
    bp = BestekpostDetail(
        nummer="02.81",
        titel="Test",
        zekerheid="laag",
        open_punten=None,
    )
    agent2 = Agent2Output(bestekposten=[bp])
    _enforce_low_confidence(agent1, agent2, "flemish")
    assert bp.open_punten is not None
    assert LOW_CONFIDENCE_WARNING["flemish"] in bp.open_punten[0]


def test_enforce_low_confidence_walloon():
    agent1 = Agent1Output(
        bestekposten=[
            Agent1Bestekpost(
                nummer="T1.11",
                image_indices=[1],
                camera_labels=["Cam 1"],
                observaties=["x"],
                zekerheid="laag",
                toelichting=None,
            )
        ]
    )
    bp = BestekpostDetail(
        nummer="T1.11",
        titel="Test",
        zekerheid="laag",
        open_punten=[],
    )
    agent2 = Agent2Output(bestekposten=[bp])
    _enforce_low_confidence(agent1, agent2, "walloon")
    assert agent2.extra_input_nodig


def test_merge_duplicates():
    agent2 = Agent2Output(
        bestekposten=[
            BestekpostDetail(
                nummer="02.81",
                titel="A",
                zekerheid="hoog",
                camera_labels=["Cam 1"],
                image_indices=[1],
                open_punten=["a"],
            ),
            BestekpostDetail(
                nummer="02.81",
                titel="B",
                zekerheid="hoog",
                camera_labels=["Cam 2"],
                image_indices=[2],
                open_punten=["b"],
            ),
        ]
    )
    _merge_duplicates(agent2)
    assert len(agent2.bestekposten) == 1
    merged = agent2.bestekposten[0]
    assert merged.camera_labels == ["Cam 1", "Cam 2"]
    assert merged.image_indices == [1, 2]
    assert set(merged.open_punten or []) == {"a", "b"}


def test_preserve_visual_references_restores_agent2_missing_fields():
    agent1 = Agent1Output(
        bestekposten=[
            Agent1Bestekpost(
                nummer="T2.22.11.3a",
                image_indices=[2, 3, 4],
                camera_labels=["Camera 1"],
                observaties=["x"],
                zekerheid="hoog",
                toelichting=None,
            )
        ]
    )
    bp = BestekpostDetail(
        nummer="T2.22.11.3a",
        titel="Poutres préfabriquées en béton armé",
        zekerheid="hoog",
        image_indices=[2, 3, 4],
        camera_labels=[],
    )
    agent2 = Agent2Output(bestekposten=[bp])

    _preserve_visual_references(agent1, agent2)

    assert bp.camera_labels == ["Camera 1"]
    assert bp.image_indices == [2, 3, 4]


def test_preserve_visual_references_does_not_overwrite_agent2_values():
    agent1 = Agent1Output(
        bestekposten=[
            Agent1Bestekpost(
                nummer="02.81",
                image_indices=[1],
                camera_labels=["Cam 1"],
                observaties=["x"],
                zekerheid="hoog",
                toelichting=None,
            )
        ]
    )
    bp = BestekpostDetail(
        nummer="02.81",
        titel="Test",
        zekerheid="hoog",
        image_indices=[9],
        camera_labels=["Manual label"],
    )
    agent2 = Agent2Output(bestekposten=[bp])

    _preserve_visual_references(agent1, agent2)

    assert bp.camera_labels == ["Manual label"]
    assert bp.image_indices == [9]
