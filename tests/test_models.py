import pytest
from pydantic import ValidationError

from app.models import Agent1Bestekpost, Agent1Output, BestekpostDetail


def test_agent1_zekerheid_pattern():
    with pytest.raises(ValidationError):
        Agent1Bestekpost(
            nummer="02",
            image_indices=[1],
            camera_labels=["Cam"],
            observaties=["x"],
            zekerheid="invalid",
            toelichting=None,
        )
    bp = Agent1Bestekpost(
        nummer="02",
        image_indices=[1],
        camera_labels=["Cam"],
        observaties=["x"],
        zekerheid="hoog",
        toelichting=None,
    )
    assert Agent1Output(bestekposten=[bp])


def test_bestekpost_detail_optional_fields():
    detail = BestekpostDetail(nummer="02.81", titel="T", zekerheid="middel")
    assert detail.image_indices is None
