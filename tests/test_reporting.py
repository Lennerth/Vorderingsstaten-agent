from app.models import Agent2Output, BestekpostDetail, BronInfo
from app.reporting import render_markdown


def test_render_markdown_includes_badges_and_timelapse():
    output = Agent2Output(
        bestekposten=[
            BestekpostDetail(
                nummer="02.81",
                titel="Test",
                zekerheid="laag",
                zichtbaar_uitgevoerd=["Werk"],
                open_punten=["Manuele check / extra foto nodig"],
            )
        ]
    )
    images = [
        (1, "Cam TL", "t=0.0", "data:image/jpeg;base64,abc"),
        (2, "Cam TL", "t=10.0", "data:image/jpeg;base64,def"),
    ]
    md = render_markdown(output, images, region="flemish")
    assert "badge-low" in md
    assert "timelapse" in md
    assert "warning-text" in md
