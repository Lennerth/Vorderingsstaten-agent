"""Knowledge-base interactions: Agent 1, detail retrieval, Agent 2."""

from __future__ import annotations

import json
import logging

from app.openai_client import (
    get_client,
    get_model,
    get_vector_store_id,
    load_prompt,
    load_schema,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent 1 – vision + file_search on master category
# ---------------------------------------------------------------------------

async def run_agent1(
    images: list[tuple[int, str, str, str]],
    bestekpost_filters: list[str] | None = None,
) -> tuple[dict, list]:
    """Return (parsed_json, file_search_annotations)."""
    client = get_client()
    vs_id = get_vector_store_id()
    instructions = load_prompt("agent1_system.txt")
    schema = load_schema("agent1.bestekpostmapping.json")

    # Build input texts
    text_lines = []
    for idx, camera_label, role, _ in images:
        text_lines.append(f"Foto {idx} = {camera_label} {role}")
    
    text_lines.append(
        "\nAnalyseer de overgang van 'voor' naar 'na' voor elke camera en geef de "
        "bestekpostnummers terug in het gevraagde JSON-formaat. "
        "Meld uitsluitend het verschil (werk uitgevoerd in deze periode), geen inventaris van de reeds bestaande staat."
    )
    if bestekpost_filters:
        joined_filters = ", ".join(bestekpost_filters)
        text_lines.append(
            "\nBeperk de output tot bestekpostnummers die binnen deze filters vallen: "
            f"{joined_filters}. Negeer waargenomen activiteit buiten deze filters."
        )
    
    content = [{"type": "input_text", "text": "\n".join(text_lines)}]
    
    # Append images
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
) -> dict:
    """Enrich Agent 1 mapping with detail fragments → structured report."""
    client = get_client()
    vs_id = get_vector_store_id()
    instructions = instructions or load_prompt("agent2_system.txt")
    schema = schema or load_schema("agent2.output.json")

    user_message = (
        "## Agent 1 analyse\n"
        "Hier zijn de gedetecteerde bestekposten. "
        "Zoek voor ELK nummer de details op in de knowledge base (gebruik file_search).\n"
        "Focus op bestanden die beginnen met 'Deel-X...' waar X overeenkomt met de eerste cijfers van het bestekpostnummer.\n\n"
        "```json\n"
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
