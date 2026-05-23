"""Knowledge-base interactions: Agent 1, detail retrieval, Agent 2."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.openai_client import (
    get_client,
    get_model,
    get_vector_store_id,
    load_region_prompt,
    load_schema,
)
from app.regions import KB_MESSAGES, normalize_region

logger = logging.getLogger(__name__)

EVIDENCE_SOURCE_TOOL_CALL = "tool_call"
EVIDENCE_SOURCE_ANNOTATION = "annotation"
EVIDENCE_SOURCE_CITATION = "citation"
EVIDENCE_SOURCE_CITATION_FALLBACK = "citation_fallback"

EVIDENCE_TEXT_KEYS = ("quote", "text", "snippet", "content", "excerpt")
EVIDENCE_SCORE_KEYS = ("score", "relevance_score", "similarity_score", "rank_score")
EVIDENCE_FALLBACK_SNIPPET_MAX_LEN = 200
RESPONSE_RETRIEVAL_INCLUDES = ["file_search_call.results"]


def _extract_usage_meta(response, t0: float) -> dict:
    usage = getattr(response, "usage", None)
    details = getattr(usage, "output_tokens_details", None) if usage is not None else None
    raw = None
    if usage is not None:
        try:
            raw = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        except Exception:
            raw = None
    return {
        "latency_s": round(time.perf_counter() - t0, 3),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        "raw_usage": raw,
    }


# ---------------------------------------------------------------------------
# Agent 1 – vision + file_search on master category
# ---------------------------------------------------------------------------

async def run_agent1(
    images: list[tuple[int, str, str, str]],
    bestekpost_filters: list[str] | None = None,
    region: str = "flemish",
) -> tuple[dict, list, dict]:
    """Return (parsed_json, retrieval_evidence, usage_meta)."""
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

    t0 = time.perf_counter()
    response, include_meta = await _create_kb_response(
        client,
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
    meta = _extract_usage_meta(response, t0)

    raw_text = _extract_text(response)
    evidence, extraction_stats = extract_retrieval_evidence(response)
    extraction_stats.update(include_meta)
    meta["evidence_extraction"] = extraction_stats

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {}

    return parsed, evidence, meta


# ---------------------------------------------------------------------------
# Agent 2 – enrichment with detail fragments
# ---------------------------------------------------------------------------

async def run_agent2(
    agent1_json: dict,
    schema: dict | None = None,
    instructions: str | None = None,
    region: str = "flemish",
) -> tuple[dict, list, dict]:
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

    t0 = time.perf_counter()
    response, include_meta = await _create_kb_response(
        client,
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
    meta = _extract_usage_meta(response, t0)

    raw_text = _extract_text(response)
    evidence, extraction_stats = extract_retrieval_evidence(response)
    extraction_stats.update(include_meta)
    meta["evidence_extraction"] = extraction_stats

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {}

    return parsed, evidence, meta


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


def _is_include_parameter_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "include" not in message:
        return False
    return any(token in message for token in ("unknown", "unsupported", "invalid", "not supported"))


def _file_search_results_present(response) -> bool:
    for output_item in getattr(response, "output", None) or []:
        if getattr(output_item, "type", None) != "file_search_call":
            continue
        results = getattr(output_item, "results", None) or []
        if results:
            return True
    return False


async def _create_kb_response(client, **create_kwargs):
    """Create a Responses API call, requesting file_search results when supported."""
    include_meta = {
        "include_requested": True,
        "include_supported": False,
        "include_payload_present": False,
    }
    try:
        response = await client.responses.create(
            include=RESPONSE_RETRIEVAL_INCLUDES,
            **create_kwargs,
        )
        include_meta["include_supported"] = True
        include_meta["include_payload_present"] = _file_search_results_present(response)
        return response, include_meta
    except Exception as exc:
        if not _is_include_parameter_error(exc):
            raise
        logger.warning(
            "Retrieval include unsupported by API; retrying without include: %s",
            exc,
        )
        response = await client.responses.create(**create_kwargs)
        include_meta["include_payload_present"] = _file_search_results_present(response)
        return response, include_meta


def _normalize_evidence_item(
    *,
    source_type: str,
    text: str | None = None,
    filename: str | None = None,
    score: float | None = None,
    raw_ref: str | None = None,
) -> dict:
    return {
        "source_type": source_type,
        "filename": filename,
        "score": score,
        "text": (text or "").strip(),
        "raw_ref": raw_ref,
    }


def _dedupe_evidence_key(item: dict) -> tuple:
    return (
        item.get("source_type"),
        item.get("filename"),
        item.get("raw_ref"),
        (item.get("text") or "")[:200],
    )


def _as_mapping(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        try:
            dumped = obj.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    return {key: getattr(obj, key) for key in dir(obj) if not key.startswith("_")}


def _first_non_empty_text(*objects: Any) -> str:
    for obj in objects:
        mapping = _as_mapping(obj)
        for key in EVIDENCE_TEXT_KEYS:
            value = mapping.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _first_numeric(*objects: Any) -> float | None:
    for obj in objects:
        mapping = _as_mapping(obj)
        for key in EVIDENCE_SCORE_KEYS:
            value = mapping.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _annotation_filename(annotation) -> str | None:
    mapping = _as_mapping(annotation)
    file_citation = mapping.get("file_citation")
    filename = (
        mapping.get("filename")
        or _as_mapping(file_citation).get("filename")
        or mapping.get("file_id")
    )
    return str(filename) if filename else None


def _annotation_raw_ref(annotation, idx: int) -> str | None:
    mapping = _as_mapping(annotation)
    raw_ref = mapping.get("file_id") or _as_mapping(mapping.get("file_citation")).get("file_id")
    return str(raw_ref) if raw_ref else f"annotation:{idx}"


def _extract_tool_call_evidence(response) -> list[dict]:
    items: list[dict] = []
    for output_item in response.output:
        if getattr(output_item, "type", None) != "file_search_call":
            continue
        results = getattr(output_item, "results", None) or []
        call_id = getattr(output_item, "id", None)
        for result in results:
            result_mapping = _as_mapping(result)
            text_parts = []
            direct_text = _first_non_empty_text(result)
            if direct_text:
                text_parts.append(direct_text)
            for chunk in result_mapping.get("content") or getattr(result, "content", None) or []:
                chunk_mapping = _as_mapping(chunk)
                if chunk_mapping.get("type") == "text":
                    chunk_text = chunk_mapping.get("text")
                    if chunk_text:
                        text_parts.append(str(chunk_text))
            filename = result_mapping.get("filename") or getattr(result, "filename", None)
            items.append(
                _normalize_evidence_item(
                    source_type=EVIDENCE_SOURCE_TOOL_CALL,
                    text="\n".join(text_parts),
                    filename=str(filename) if filename else None,
                    score=_first_numeric(result),
                    raw_ref=str(call_id) if call_id else None,
                )
            )
    return items


def _annotation_source_type(annotation) -> str:
    ann_type = getattr(annotation, "type", None) or ""
    if "citation" in ann_type:
        return EVIDENCE_SOURCE_CITATION
    return EVIDENCE_SOURCE_ANNOTATION


def _extract_annotation_text(annotation, full_text: str) -> str:
    mapping = _as_mapping(annotation)
    file_citation = mapping.get("file_citation")
    direct = _first_non_empty_text(annotation, file_citation)
    if direct:
        return direct

    start = mapping.get("start_index")
    end = mapping.get("end_index")
    if (
        full_text
        and start is not None
        and end is not None
        and 0 <= int(start) < int(end) <= len(full_text)
    ):
        return full_text[int(start) : int(end)].strip()
    return ""


def _extract_annotation_score(annotation) -> float | None:
    mapping = _as_mapping(annotation)
    file_citation = mapping.get("file_citation")
    containers = [annotation, file_citation, mapping.get("file_search_result")]
    return _first_numeric(*containers)


def _backfill_from_tool_call_hits(items: list[dict]) -> list[dict]:
    """Propagate upstream tool_call score/text to matching hits for the same filename."""
    tool_data_by_file: dict[str, dict[str, Any]] = {}
    for item in items:
        if item.get("source_type") != EVIDENCE_SOURCE_TOOL_CALL:
            continue
        filename = _normalize_filename(item.get("filename"))
        if not filename:
            continue
        existing = tool_data_by_file.get(filename, {})
        if item.get("score") is not None:
            existing["score"] = item["score"]
        if (item.get("text") or "").strip():
            existing["text"] = item["text"]
        tool_data_by_file[filename] = existing

    enriched: list[dict] = []
    for item in items:
        updated = dict(item)
        filename = _normalize_filename(updated.get("filename"))
        tool_data = tool_data_by_file.get(filename)
        if tool_data:
            if updated.get("score") is None and tool_data.get("score") is not None:
                updated["score"] = tool_data["score"]
            if not (updated.get("text") or "").strip() and (tool_data.get("text") or "").strip():
                updated["text"] = tool_data["text"]
        enriched.append(updated)
    return enriched


def _score_source_type_breakdown(items: list[dict]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for item in items:
        if item.get("score") is None:
            continue
        source_type = item.get("source_type") or "unknown"
        breakdown[source_type] = breakdown.get(source_type, 0) + 1
    return breakdown


def _extract_message_annotation_evidence(response) -> list[dict]:
    items: list[dict] = []
    for output_item in response.output:
        if getattr(output_item, "type", None) != "message":
            continue
        for content in getattr(output_item, "content", None) or []:
            if getattr(content, "type", None) != "output_text":
                continue
            full_text = getattr(content, "text", "") or ""
            annotations = getattr(content, "annotations", None) or []
            for idx, annotation in enumerate(annotations):
                items.append(
                    _normalize_evidence_item(
                        source_type=_annotation_source_type(annotation),
                        text=_extract_annotation_text(annotation, full_text),
                        filename=_annotation_filename(annotation),
                        score=_extract_annotation_score(annotation),
                        raw_ref=_annotation_raw_ref(annotation, idx),
                    )
                )
    return items


def extract_retrieval_evidence(response) -> tuple[list[dict], dict]:
    """Extract normalized retrieval evidence from multiple response shapes."""
    tool_hits = _extract_tool_call_evidence(response)
    annotation_hits = _extract_message_annotation_evidence(response)

    merged: list[dict] = []
    seen: set[tuple] = set()
    by_source_type: dict[str, int] = {
        EVIDENCE_SOURCE_TOOL_CALL: 0,
        EVIDENCE_SOURCE_ANNOTATION: 0,
        EVIDENCE_SOURCE_CITATION: 0,
    }

    for item in tool_hits + annotation_hits:
        key = _dedupe_evidence_key(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        source_type = item.get("source_type") or EVIDENCE_SOURCE_ANNOTATION
        by_source_type[source_type] = by_source_type.get(source_type, 0) + 1

    merged = _backfill_from_tool_call_hits(merged)
    fallback_used = len(tool_hits) == 0 and len(annotation_hits) > 0
    quality = summarize_evidence_items(merged)
    stats = {
        "total_hits": len(merged),
        "tool_call_hits": len(tool_hits),
        "annotation_hits": len(annotation_hits),
        "by_source_type": by_source_type,
        "fallback_used": fallback_used,
        "empty_text_hits": quality["empty_text_hits"],
        "null_score_hits": quality["null_score_hits"],
        "fallback_derived_hits": quality["fallback_derived_hits"],
        "score_available_hits": quality["with_score"],
        "score_missing_hits": quality["null_score_hits"],
        "score_source_type_breakdown": quality["score_source_type_breakdown"],
        "include_payload_present": _file_search_results_present(response),
    }
    return merged, stats


def _normalize_filename(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().casefold()


def _first_provenance_fragment(bestekposten: list[dict], filename: str | None) -> str:
    target = _normalize_filename(filename)
    if not target:
        return ""
    for post in bestekposten:
        bron = post.get("bron") or {}
        bron_filename = _normalize_filename(bron.get("bestandsnaam"))
        if bron_filename and bron_filename != target:
            continue
        fragmenten = bron.get("fragmenten") or []
        for fragment in fragmenten:
            text = str(fragment).strip().strip('"')
            if text:
                return text[:EVIDENCE_FALLBACK_SNIPPET_MAX_LEN]
    return ""


def enrich_evidence_with_provenance_fallback(
    items: list[dict],
    bestekposten: list[dict],
) -> list[dict]:
    """Fill missing citation text from model-reported bron.fragmenten when available."""
    enriched: list[dict] = []
    for item in items:
        updated = dict(item)
        if (updated.get("text") or "").strip():
            enriched.append(updated)
            continue

        fallback_text = _first_provenance_fragment(bestekposten, updated.get("filename"))
        if not fallback_text:
            enriched.append(updated)
            continue

        raw_ref = updated.get("raw_ref") or "unknown"
        updated["text"] = fallback_text
        updated["source_type"] = EVIDENCE_SOURCE_CITATION_FALLBACK
        updated["raw_ref"] = f"provenance_fallback:{raw_ref}"
        enriched.append(updated)
    return enriched


def summarize_evidence_items(items: list[dict]) -> dict[str, Any]:
    """Compute quality metrics for normalized evidence items."""
    if not items:
        return {
            "count": 0,
            "with_text": 0,
            "with_filename": 0,
            "with_score": 0,
            "empty_text_hits": 0,
            "null_score_hits": 0,
            "fallback_derived_hits": 0,
            "text_ratio": 0.0,
            "filename_ratio": 0.0,
            "score_ratio": 0.0,
            "fallback_ratio": 0.0,
            "by_source_type": {},
            "score_source_type_breakdown": {},
        }

    with_text = sum(1 for item in items if (item.get("text") or "").strip())
    with_filename = sum(1 for item in items if item.get("filename"))
    with_score = sum(1 for item in items if item.get("score") is not None)
    empty_text_hits = len(items) - with_text
    null_score_hits = len(items) - with_score
    fallback_derived_hits = sum(
        1 for item in items if item.get("source_type") == EVIDENCE_SOURCE_CITATION_FALLBACK
    )
    by_source_type: dict[str, int] = {}
    for item in items:
        source_type = item.get("source_type") or "unknown"
        by_source_type[source_type] = by_source_type.get(source_type, 0) + 1

    count = len(items)
    return {
        "count": count,
        "with_text": with_text,
        "with_filename": with_filename,
        "with_score": with_score,
        "empty_text_hits": empty_text_hits,
        "null_score_hits": null_score_hits,
        "fallback_derived_hits": fallback_derived_hits,
        "text_ratio": round(with_text / count, 3),
        "filename_ratio": round(with_filename / count, 3),
        "score_ratio": round(with_score / count, 3),
        "fallback_ratio": round(fallback_derived_hits / count, 3),
        "by_source_type": by_source_type,
        "score_source_type_breakdown": _score_source_type_breakdown(items),
    }
