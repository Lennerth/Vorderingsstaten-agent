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

async def run_agent1(before_b64_url: str, after_b64_url: str) -> tuple[dict, list]:
    """Return (parsed_json, file_search_annotations)."""
    client = get_client()
    vs_id = get_vector_store_id()
    instructions = load_prompt("agent1_system.txt")
    schema = load_schema("agent1.bestekpostmapping.json")

    response = await client.responses.create(
        model=get_model(),
        instructions=instructions,
        temperature=0.0,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": before_b64_url},
                    {"type": "input_image", "image_url": after_b64_url},
                    {
                        "type": "input_text",
                        "text": (
                            "Foto 1 = voor (eerder), Foto 2 = na (later). "
                            "Analyseer de overgang Foto 1 → Foto 2 en geef de "
                            "bestekpostnummers terug in het gevraagde JSON-formaat."
                        ),
                    },
                ],
            }
        ],
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
    return json.loads(raw_text), annotations


# ---------------------------------------------------------------------------
# Detail retrieval – direct vector-store search (no model inference)
# ---------------------------------------------------------------------------

async def search_details(
    bestekpostnummer: str,
    observaties: list[str],
    deel: int,
) -> list[dict]:
    """Search the detail vector store for fragments matching a bestekpost."""
    client = get_client()
    vs_id = get_vector_store_id()

    keywords = " ".join(observaties[:3]) if observaties else ""
    query = f"bestekpost {bestekpostnummer} {keywords}".strip()

    try:
        search_results = await client.vector_stores.search(
            vector_store_id=vs_id,
            query=query,
            filters={
                "type": "and",
                "filters": [
                    {"type": "eq", "key": "category", "value": "details"},
                    {"type": "eq", "key": "deel", "value": str(deel)},
                ],
            },
            max_num_results=5,
        )

        fragments: list[dict] = []
        for result in search_results.data:
            text_parts = []
            for chunk in result.content:
                if chunk.type == "text":
                    text_parts.append(chunk.text)
            fragments.append(
                {
                    "text": "\n".join(text_parts),
                    "filename": result.filename,
                    "score": result.score,
                }
            )
        return fragments

    except Exception:
        logger.exception("Detail search failed for %s (deel=%d)", bestekpostnummer, deel)
        return []


# ---------------------------------------------------------------------------
# Agent 2 – enrichment with detail fragments
# ---------------------------------------------------------------------------

async def run_agent2(agent1_json: dict) -> dict:
    """Enrich Agent 1 mapping with detail fragments → structured report."""
    client = get_client()
    vs_id = get_vector_store_id()
    instructions = load_prompt("agent2_system.txt")
    schema = load_schema("agent2.output.json")

    user_message = (
        "## Agent 1 analyse\n"
        "Hier zijn de gedetecteerde bestekpostnummers. "
        "Zoek voor ELK nummer de details op in de knowledge base (gebruik file_search).\n"
        "Focus op bestanden die beginnen met 'Deel-X...' waar X overeenkomt met de eerste cijfers van het bestekpostnummer.\n\n"
        "```json\n"
        + json.dumps(agent1_json, indent=2, ensure_ascii=False)
        + "\n```\n"
    )

    response = await client.responses.create(
        model=get_model(),
        instructions=instructions,
        input=[{"role": "user", "content": user_message}],
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [vs_id],
                # We can't easily filter by metadata per-item here without multiple turns,
                # so we trust the model/retriever to find the right "Deel-X" files based on content/filename match.
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
    return json.loads(raw_text)


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
