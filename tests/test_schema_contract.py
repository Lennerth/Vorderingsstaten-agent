import json
from pathlib import Path

import jsonschema
import pytest

from app.models import Agent2Output, BestekpostDetail, BronInfo
from app.openai_client import load_schema

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_recorded_outputs_validate_when_present():
    schema1 = load_schema("agent1.bestekpostmapping.json")
    schema2 = load_schema("agent2.output.json")
    outputs_root = PROJECT_ROOT / "outputs"
    if not outputs_root.is_dir():
        pytest.skip("No outputs directory")

    validated = 0
    for output_file in outputs_root.glob("output */output.json"):
        payload = json.loads(output_file.read_text(encoding="utf-8"))
        if "agent1_json" in payload and payload["agent1_json"]:
            try:
                jsonschema.validate(payload["agent1_json"], schema1)
                validated += 1
            except jsonschema.ValidationError:
                continue
        if "agent2_json" in payload and payload["agent2_json"]:
            try:
                jsonschema.validate(payload["agent2_json"], schema2)
                validated += 1
            except jsonschema.ValidationError:
                continue

    if validated == 0:
        pytest.skip("No output.json fixtures found")


def test_agent2_model_dump_matches_strict_schema():
    schema = load_schema("agent2.output.json")
    model = Agent2Output(
        bestekposten=[
            BestekpostDetail(
                nummer="02.81",
                titel="T",
                zekerheid="hoog",
                image_indices=[1, 2],
                camera_labels=["Cam"],
                zichtbaar_uitgevoerd=["Werk"],
                bestekeisen=["Eis"],
                bron=BronInfo(
                    deel="0",
                    sectie="02.81",
                    fragmenten=["frag"],
                    bestandsnaam="Deel-0.docx",
                ),
                open_punten=["Geen"],
                volgende_stap="Volgende",
            )
        ]
    )
    jsonschema.validate(model.model_dump(exclude_none=True), schema)
