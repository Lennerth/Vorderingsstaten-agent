"""Pipeline: image optimization → Agent 1 → Agent 2 → markdown."""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import time

from app.kb import run_agent1, run_agent2
from app.logging_utils import RequestLogger
from app.models import Agent1Output, Agent2Output
from app.openai_client import load_prompt, load_schema
from app.reporting import render_markdown
from app.utils.image_processing import optimize_and_encode

logger = logging.getLogger(__name__)

ALWAYS_REQUIRED_AGENT2_FIELDS = {"nummer", "titel", "zekerheid"}
OPTIONAL_AGENT2_FIELDS = {
    "zichtbaar_uitgevoerd",
    "bestekeisen",
    "bron",
    "image_indices",
    "camera_labels",
    "open_punten",
    "volgende_stap",
}


class InvalidBestekpostFilter(ValueError):
    """Raised when a bestekpost filter cannot be parsed safely."""


async def run_pipeline(
    camera_pairs: list[dict],
    request_id: str,
    bestekpost_filter: list[str] | None = None,
    report_fields: list[str] | None = None,
) -> dict:
    rlog = RequestLogger(request_id)
    t_start = time.time()

    # ── 1. Image optimisation ────────────────────────────────────────────
    logger.info("[%s] Optimizing images for %d cameras …", request_id, len(camera_pairs))
    
    tasks = []
    for pair in camera_pairs:
        tasks.append(asyncio.to_thread(optimize_and_encode, pair["before_bytes"]))
        tasks.append(asyncio.to_thread(optimize_and_encode, pair["after_bytes"]))
    
    results = await asyncio.gather(*tasks)
    
    images = []
    sizes_log = []
    idx = 1
    
    for i, pair in enumerate(camera_pairs):
        before_url, before_size = results[i*2]
        after_url, after_size = results[i*2 + 1]
        camera_label = pair["camera_label"]
        
        images.append((idx, camera_label, "voor", before_url))
        idx += 1
        images.append((idx, camera_label, "na", after_url))
        idx += 1
        
        sizes_log.append({
            "camera_label": camera_label,
            "before_size": before_size,
            "after_size": after_size
        })

    rlog.log_step("image_optimization", {"sizes": sizes_log})
    rlog.add_timing("image_optimization", time.time() - t_start)

    # ── 2. Agent 1: vision + master file_search ──────────────────────────
    logger.info("[%s] Running Agent 1 …", request_id)
    t1 = time.time()
    parsed_filters = _parse_bestekpost_filters(bestekpost_filter or [])
    agent1_raw, agent1_annotations = await run_agent1(images, bestekpost_filter)
    rlog.log_step("agent1_raw_output", {"output": agent1_raw})

    try:
        agent1 = Agent1Output.model_validate(agent1_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 1 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent1_retry", {"error": str(exc)})
        agent1_raw, agent1_annotations = await run_agent1(images, bestekpost_filter)
        agent1 = Agent1Output.model_validate(agent1_raw)

    if parsed_filters:
        before_filter = len(agent1.bestekposten)
        removed = [
            bp.nummer
            for bp in agent1.bestekposten
            if not _bestekpost_matches_filter(bp.nummer, parsed_filters)
        ]
        agent1.bestekposten = [
            bp
            for bp in agent1.bestekposten
            if _bestekpost_matches_filter(bp.nummer, parsed_filters)
        ]
        agent1_raw = agent1.model_dump()
        rlog.log_step(
            "agent1_filtered",
            {
                "before_count": before_filter,
                "after_count": len(agent1.bestekposten),
                "removed": removed,
                "reason": "outside_filter_range",
            },
        )

    rlog.add_timing("agent1", time.time() - t1)
    total_posts = len(agent1.bestekposten)
    logger.info("[%s] Agent 1 returned %d bestekposten", request_id, total_posts)

    # ── 3. Detail retrieval (via Agent 2 internal tool use) ────────────────
    # We skip explicit parallel retrieval because Azure doesn't support
    # client.vector_stores.search() directly. We let Agent 2 do it.

    # ── 4. Agent 2: enrichment ───────────────────────────────────────────
    logger.info("[%s] Running Agent 2 (with file_search) …", request_id)
    t3 = time.time()
    selected_report_fields = set(
        OPTIONAL_AGENT2_FIELDS if report_fields is None else report_fields
    )
    agent2_schema = _build_agent2_schema(selected_report_fields)
    agent2_instructions = _build_agent2_instructions(selected_report_fields)
    agent2_raw = await run_agent2(
        agent1_raw,
        schema=agent2_schema,
        instructions=agent2_instructions,
    )
    rlog.log_step("agent2_raw_output", {"output": agent2_raw})

    try:
        agent2 = Agent2Output.model_validate(agent2_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 2 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent2_retry", {"error": str(exc)})
        agent2_raw = await run_agent2(
            agent1_raw,
            schema=agent2_schema,
            instructions=agent2_instructions,
        )
        agent2 = Agent2Output.model_validate(agent2_raw)

    _enforce_low_confidence(agent1, agent2)
    
    # Sort agent2 bestekposten by nummer before rendering
    agent2.bestekposten.sort(key=lambda x: x.nummer)
    
    # Defensive merge of bestekposten (if model emits duplicates)
    _merge_duplicates(agent2)

    rlog.add_timing("agent2", time.time() - t3)

    # ── 5. Render markdown ───────────────────────────────────────────────
    markdown = render_markdown(agent2, images)

    total_time = time.time() - t_start
    rlog.add_timing("total", total_time)
    logger.info("[%s] Pipeline complete in %.1f s", request_id, total_time)

    rlog.log_step("pipeline_complete", {"total_s": round(total_time, 2)})
    rlog.persist()

    return {
        "markdown_report": markdown,
        "agent2_json": agent2.model_dump(exclude_none=True),
        "agent1_json": agent1.model_dump(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOW_WARNING = "Manuele check / extra foto nodig"

def _enforce_low_confidence(agent1: Agent1Output, agent2: Agent2Output) -> None:
    low_posts = {
        bp.nummer: bp.camera_labels
        for bp in agent1.bestekposten
        if bp.zekerheid == "laag"
    }
    
    if not low_posts:
        return

    for bp in agent2.bestekposten:
        if bp.nummer not in low_posts:
            continue

        if bp.open_punten is not None and _LOW_WARNING.lower() not in " ".join(bp.open_punten).lower():
            bp.open_punten.append(_LOW_WARNING)

        cameras_str = ", ".join(low_posts[bp.nummer])
        warning_msg = f"Bestekpost {bp.nummer} ({cameras_str}): {_LOW_WARNING}"
        
        if not any(_LOW_WARNING.lower() in item.lower() and bp.nummer in item for item in agent2.extra_input_nodig):
            agent2.extra_input_nodig.append(warning_msg)


def _merge_duplicates(agent2: Agent2Output) -> None:
    merged = {}
    for bp in agent2.bestekposten:
        if bp.nummer not in merged:
            merged[bp.nummer] = bp
        else:
            existing = merged[bp.nummer]
            if bp.camera_labels is not None:
                if existing.camera_labels is None:
                    existing.camera_labels = []
                for label in bp.camera_labels:
                    if label not in existing.camera_labels:
                        existing.camera_labels.append(label)
            if bp.image_indices is not None:
                if existing.image_indices is None:
                    existing.image_indices = []
                for idx in bp.image_indices:
                    if idx not in existing.image_indices:
                        existing.image_indices.append(idx)
            if bp.open_punten is not None:
                if existing.open_punten is None:
                    existing.open_punten = []
                for point in bp.open_punten:
                    if point not in existing.open_punten:
                        existing.open_punten.append(point)
                    
    agent2.bestekposten = list(merged.values())
    agent2.bestekposten.sort(key=lambda x: x.nummer)


def _parse_bestekpost_filters(filters: list[str]) -> list[dict]:
    parsed = []
    for raw_filter in filters:
        if "-" in raw_filter:
            start_raw, end_raw = [part.strip() for part in raw_filter.split("-", 1)]
            start = _parse_bestekpost_prefix(start_raw)
            end = _parse_bestekpost_prefix(end_raw)
            if len(start) != len(end):
                raise InvalidBestekpostFilter(
                    f"Invalid bestekpost filter '{raw_filter}': range endpoints must have the same depth."
                )
            if start > end:
                raise InvalidBestekpostFilter(
                    f"Invalid bestekpost filter '{raw_filter}': range start must be before range end."
                )
            parsed.append({"type": "range", "start": start, "end": end, "depth": len(start), "raw": raw_filter})
        else:
            prefix = _parse_bestekpost_prefix(raw_filter)
            parsed.append({"type": "exact", "prefix": prefix, "depth": len(prefix), "raw": raw_filter})
    return parsed


def _bestekpost_matches_filter(nummer: str, parsed_filters: list[dict]) -> bool:
    nummer_segments = _parse_bestekpost_number(nummer)
    for parsed_filter in parsed_filters:
        depth = parsed_filter["depth"]
        if len(nummer_segments) < depth:
            continue
        candidate = nummer_segments[:depth]
        if parsed_filter["type"] == "exact" and candidate == parsed_filter["prefix"]:
            return True
        if parsed_filter["type"] == "range" and parsed_filter["start"] <= candidate <= parsed_filter["end"]:
            return True
    return False


def _parse_bestekpost_prefix(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})?", value):
        raise InvalidBestekpostFilter(
            f"Invalid bestekpost filter '{value}'. Use forms like '05', '05.82', or '05.82-05.89'."
        )
    return tuple(int(part) for part in value.split("."))


def _parse_bestekpost_number(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d{1,2}(?:\.\d{1,2})*", value):
        return ()
    return tuple(int(part) for part in value.split("."))


def _build_agent2_schema(report_fields: set[str]) -> dict:
    schema = copy.deepcopy(load_schema("agent2.output.json"))
    item_schema = schema["properties"]["bestekposten"]["items"]
    properties = item_schema.get("properties", {})

    for field in OPTIONAL_AGENT2_FIELDS - report_fields:
        properties.pop(field, None)

    item_schema["required"] = [
        field
        for field in item_schema.get("required", [])
        if field in ALWAYS_REQUIRED_AGENT2_FIELDS or field in report_fields
    ]
    return schema


def _build_agent2_instructions(report_fields: set[str]) -> str:
    base_prompt = load_prompt("agent2_system.txt")
    active_fields = sorted(ALWAYS_REQUIRED_AGENT2_FIELDS | report_fields)
    inactive_fields = sorted(OPTIONAL_AGENT2_FIELDS - report_fields)
    return (
        f"{base_prompt}\n\n"
        "## Actieve velden\n"
        "Vul uitsluitend velden in die in het actieve JSON-schema staan.\n"
        f"Actieve bestekpostvelden: {', '.join(active_fields)}.\n"
        f"Niet-actieve optionele velden: {', '.join(inactive_fields) if inactive_fields else 'geen'}.\n"
        "Als een optioneel veld niet actief is, vermeld de informatie voor dat veld nergens anders."
    )
