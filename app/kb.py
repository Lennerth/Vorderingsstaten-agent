"""Knowledge-base interactions: Agent 1, detail retrieval, Agent 2."""

from __future__ import annotations

import json
import logging

from app.openai_client import (
    get_client,
    get_model,
    get_vector_store_id,
    load_region_prompt,
    load_schema,
)
from app.regions import KB_MESSAGES, normalize_region

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent 1 – vision + file_search on master category
# ---------------------------------------------------------------------------

async def run_agent1(
    images: list[tuple[int, str, str, str]],
    bestekpost_filters: list[str] | None = None,
    region: str = "flemish",
) -> tuple[dict, list]:
    """Return (parsed_json, file_search_annotations)."""
    region = normalize_region(region)
    client = get_client()
    vs_id = get_vector_store_id(region)
    instructions = load_region_prompt("agent1", region)
    schema = load_schema("agent1.bestekpostmapping.json")
    msgs = KB_MESSAGES[region]
    roles = msgs["roles"]

    text_lines = []
    for idx, camera_label, role, _ in images:
        role_label = roles.get(role, role)
        text_lines.append(
            msgs["photo_line"].format(idx=idx, camera=camera_label, role=role_label)
        )

    text_lines.append(msgs["analysis_instruction"])
    if bestekpost_filters:
        joined_filters = ", ".join(bestekpost_filters)
        text_lines.append(msgs["filter_prefix"].format(filters=joined_filters))

    content = [{"type": "input_text", "text": "\n".join(text_lines)}]

    for _, _, _, data_url in images:
        content.append({"type": "input_image", "image_url": data_url})

    response = await client.responses.create(
        model=get_model(),
        reasoning={"effort": "high"},
        instructions=instructions,
        input=[{"role": "user", "content": content}],
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [vs_id],
                "filters": {
                    "type": "eq",
                    "key": "category",
                    "value": "master",
                },
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "bestekpost_mapping",
                "schema": schema,
                "strict": True,
            }
        },
    )

    raw_text = _extract_text(response)
    annotations = _extract_file_search_annotations(response)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {}

    return parsed, annotations


# ---------------------------------------------------------------------------
# Agent 2 – enrichment with detail fragments
# ---------------------------------------------------------------------------

async def run_agent2(
    agent1_json: dict,
    schema: dict | None = None,
    instructions: str | None = None,
    region: str = "flemish",
) -> dict:
    """Enrich Agent 1 mapping with detail fragments → structured report."""
    region = normalize_region(region)
    client = get_client()
    vs_id = get_vector_store_id(region)
    instructions = instructions or load_region_prompt("agent2", region)
    schema = schema or load_schema("agent2.output.json")
    msgs = KB_MESSAGES[region]

    user_message = (
        msgs["agent2_intro"]
        + "```json\n"
        + json.dumps(agent1_json, indent=2, ensure_ascii=False)
        + "\n```\n"
    )

    response = await client.responses.create(
        model=get_model(),
        reasoning={"effort": "high"},
        instructions=instructions,
        input=[{"role": "user", "content": user_message}],
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [vs_id],
                "filters": {
                    "type": "eq",
                    "key": "category",
                    "value": "details",
                },
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "vorderingsstaat_rapport",
                "schema": schema,
                "strict": True,
            }
        },
    )

    raw_text = _extract_text(response)
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {}

    return parsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text(response) -> str:
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    return content.text
    return "{}"


def _extract_file_search_annotations(response) -> list[dict]:
    annotations: list[dict] = []
    for item in response.output:
        if item.type == "file_search_call":
            if not item.results:
                continue
            for r in item.results:
                text_parts = []
                for chunk in r.content:
                    if chunk.type == "text":
                        text_parts.append(chunk.text)
                annotations.append(
                    {
                        "text": "\n".join(text_parts),
                        "filename": r.filename,
                        "score": r.score,
                    }
                )
    return annotations
