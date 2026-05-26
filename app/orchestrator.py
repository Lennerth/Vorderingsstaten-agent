"""Pipeline: image optimization → Agent 1 → Agent 2 → markdown."""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import time
from collections.abc import Callable

from app.kb import (
    enrich_evidence_with_provenance_fallback,
    run_agent1,
    run_agent2,
    summarize_evidence_items,
)
from app.logging_utils import RequestLogger, format_timings_display
from app.models import Agent1Output, Agent2Output
from app.openai_client import load_region_prompt, load_schema
from app.regions import (
    KB_MESSAGES,
    LOW_CONFIDENCE_MESSAGE,
    LOW_CONFIDENCE_WARNING,
    normalize_region,
)
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
    camera_inputs: list[dict],
    request_id: str,
    bestekpost_filter: list[str] | None = None,
    report_fields: list[str] | None = None,
    region: str = "flemish",
    compression_options: dict | None = None,
    progress_callback: Callable[..., None] | None = None,
) -> dict:
    region = normalize_region(region)
    rlog = RequestLogger(request_id)
    t_start = time.time()
    rlog.log_step("region", {"region": region})

    def _progress(step_id: str, status: str, **extra):
        if progress_callback:
            progress_callback(step_id, status, **extra)

    # ── 1. Image optimisation ────────────────────────────────────────────
    _progress("image_optimization", "running")
    opts = compression_options or {}
    logger.info(
        "[%s] Optimizing images for %d camera track(s) (compression mode=%s preset=%s quality=%s target_mb=%s) …",
        request_id,
        len(camera_inputs),
        opts.get("mode", "default"),
        opts.get("preset"),
        opts.get("quality"),
        opts.get("target_image_mb"),
    )

    tasks: list = []
    task_meta: list[tuple[str, str, str | None]] = []

    for track in camera_inputs:
        kind = track.get("kind", "pair")
        label = track["camera_label"]
        if kind == "pair":
            tasks.append(asyncio.to_thread(optimize_and_encode, track["before_bytes"], opts))
            task_meta.append((label, "voor", None))
            tasks.append(asyncio.to_thread(optimize_and_encode, track["after_bytes"], opts))
            task_meta.append((label, "na", None))
        elif kind == "timelapse":
            for frame in track["frames"]:
                tasks.append(
                    asyncio.to_thread(optimize_and_encode, frame["jpeg_bytes"], opts)
                )
                task_meta.append((label, "timelapse", frame["timestamp_s"]))
        else:
            raise ValueError(f"Unknown camera input kind: {kind!r}")

    results = await asyncio.gather(*tasks)

    images: list[tuple[int, str, str, str]] = []
    sizes_log: list[dict] = []
    extracted_frames_payload: list[dict] = []
    idx = 1
    track_sizes: dict[str, dict] = {}

    for (label, role_kind, timestamp_s), (data_url, size_str, meta) in zip(
        task_meta, results
    ):
        if role_kind == "timelapse":
            role = f"t={timestamp_s:.1f}"
        else:
            role = role_kind

        images.append((idx, label, role, data_url))

        if role_kind == "timelapse":
            track_entry = track_sizes.setdefault(
                label,
                {"camera_label": label, "kind": "timelapse", "frames": []},
            )
            track_entry["frames"].append(
                {
                    "idx": idx,
                    "timestamp_s": timestamp_s,
                    "size": size_str,
                    "compression": meta,
                    "data_url": data_url,
                }
            )
        elif role_kind == "voor":
            track_sizes[label] = {
                "camera_label": label,
                "kind": "pair",
                "before_size": size_str,
                "before_compression": meta,
            }
        elif role_kind == "na":
            entry = track_sizes.get(label, {"camera_label": label, "kind": "pair"})
            entry["after_size"] = size_str
            entry["after_compression"] = meta
            track_sizes[label] = entry

        idx += 1

    sizes_log = list(track_sizes.values())

    extracted_frames_response = [
        {
            "camera_label": entry["camera_label"],
            "frames": [
                {
                    "idx": frame["idx"],
                    "timestamp_s": frame["timestamp_s"],
                    "data_url": frame["data_url"],
                }
                for frame in entry.get("frames", [])
            ],
        }
        for entry in sizes_log
        if entry.get("kind") == "timelapse"
    ]

    rlog.log_step("image_optimization", {"sizes": sizes_log, "compression_options": opts})
    rlog.add_timing("image_optimization", time.time() - t_start)
    _progress("image_optimization", "done", duration_s=time.time() - t_start)

    # ── 2. Agent 1: vision + master file_search ──────────────────────────
    _progress("agent1", "running")
    logger.info("[%s] Running Agent 1 …", request_id)
    t1 = time.time()
    parsed_filters = _parse_bestekpost_filters(bestekpost_filter or [])
    agent1_raw, agent1_annotations, agent1_meta = await run_agent1(
        images, bestekpost_filter, region=region
    )
    rlog.log_step("agent1_usage", agent1_meta)
    rlog.add_tokens(agent1_meta)
    rlog.log_step("agent1_raw_output", {"output": agent1_raw})

    try:
        agent1 = Agent1Output.model_validate(agent1_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 1 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent1_retry", {"error": str(exc)})
        agent1_raw, agent1_annotations, agent1_meta = await run_agent1(
            images, bestekpost_filter, region=region
        )
        rlog.log_step("agent1_retry_usage", agent1_meta)
        rlog.add_tokens(agent1_meta)
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

    rlog.log_step("agent1_retrieval", {"hits": len(agent1_annotations)})
    rlog.add_timing("agent1", time.time() - t1)
    _progress("agent1", "done", duration_s=time.time() - t1)
    total_posts = len(agent1.bestekposten)
    logger.info("[%s] Agent 1 returned %d bestekposten", request_id, total_posts)

    # ── 3. Detail retrieval (via Agent 2 internal tool use) ────────────────
    # We skip explicit parallel retrieval because Azure doesn't support
    # client.vector_stores.search() directly. We let Agent 2 do it.

    # ── 4. Agent 2: enrichment ───────────────────────────────────────────
    _progress("agent2", "running")
    logger.info("[%s] Running Agent 2 (with file_search) …", request_id)
    t3 = time.time()
    selected_report_fields = set(
        OPTIONAL_AGENT2_FIELDS if report_fields is None else report_fields
    )
    agent2_schema = _build_agent2_schema(selected_report_fields)
    agent2_instructions = _build_agent2_instructions(
        selected_report_fields, region=region
    )
    agent2_raw, agent2_annotations, agent2_meta = await run_agent2(
        agent1_raw,
        schema=agent2_schema,
        instructions=agent2_instructions,
        region=region,
    )
    rlog.log_step("agent2_usage", agent2_meta)
    rlog.add_tokens(agent2_meta)
    rlog.log_step("agent2_raw_output", {"output": agent2_raw})

    try:
        agent2 = Agent2Output.model_validate(agent2_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 2 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent2_retry", {"error": str(exc)})
        agent2_raw, agent2_annotations, agent2_meta = await run_agent2(
            agent1_raw,
            schema=agent2_schema,
            instructions=agent2_instructions,
            region=region,
        )
        rlog.log_step("agent2_retry_usage", agent2_meta)
        rlog.add_tokens(agent2_meta)
        rlog.log_step("agent2_retry_raw_output", {"output": agent2_raw})
        agent2 = Agent2Output.model_validate(agent2_raw)
    agent2_annotations = enrich_evidence_with_provenance_fallback(
        agent2_annotations,
        agent2_raw.get("bestekposten") or [],
    )
    agent2_quality = summarize_evidence_items(agent2_annotations)
    agent2_extraction = agent2_meta.get("evidence_extraction", {})
    rlog.log_step(
        "agent2_retrieval",
        {
            "hits": len(agent2_annotations),
            **agent2_extraction,
            "quality": agent2_quality,
            "empty_text_hits": agent2_quality["empty_text_hits"],
            "null_score_hits": agent2_quality["null_score_hits"],
            "fallback_derived_hits": agent2_quality["fallback_derived_hits"],
            "score_available_hits": agent2_quality["with_score"],
            "score_missing_hits": agent2_quality["null_score_hits"],
            "score_source_type_breakdown": agent2_quality["score_source_type_breakdown"],
            "include_payload_present": agent2_extraction.get("include_payload_present", False),
        },
    )

    _preserve_visual_references(agent1, agent2)
    _enforce_low_confidence(agent1, agent2, region)
    
    # Sort agent2 bestekposten by nummer before rendering
    agent2.bestekposten.sort(key=lambda x: x.nummer)
    
    # Defensive merge of bestekposten (if model emits duplicates)
    _merge_duplicates(agent2)

    rlog.add_timing("agent2", time.time() - t3)
    _progress("agent2", "done", duration_s=time.time() - t3)

    # ── 5. Render markdown ───────────────────────────────────────────────
    _progress("report_generation", "running")
    t_report = time.time()
    markdown = render_markdown(agent2, images, region=region)

    total_time = time.time() - t_start
    rlog.add_timing("total", total_time)
    _progress("report_generation", "done", duration_s=time.time() - t_report)
    logger.info("[%s] Pipeline complete in %s", request_id, format_timings_display({"total": total_time})["total"])

    rlog.log_step("pipeline_complete", {"total_s": round(total_time, 2)})
    agent1_quality = summarize_evidence_items(agent1_annotations)
    agent1_extraction = agent1_meta.get("evidence_extraction", {})
    agent2_extraction = agent2_meta.get("evidence_extraction", {})
    rlog.log_step(
        "retrieval_evidence",
        {
            "agent1_hits": len(agent1_annotations),
            "agent2_hits": len(agent2_annotations),
            "agent1_extraction": agent1_extraction,
            "agent2_extraction": agent2_extraction,
            "agent1_quality": agent1_quality,
            "agent2_quality": agent2_quality,
            "agent1_empty_text_hits": agent1_quality["empty_text_hits"],
            "agent1_null_score_hits": agent1_quality["null_score_hits"],
            "agent1_fallback_derived_hits": agent1_quality["fallback_derived_hits"],
            "agent1_score_available_hits": agent1_quality["with_score"],
            "agent1_score_missing_hits": agent1_quality["null_score_hits"],
            "agent1_score_source_type_breakdown": agent1_quality["score_source_type_breakdown"],
            "agent1_include_payload_present": agent1_extraction.get("include_payload_present", False),
            "agent2_empty_text_hits": agent2_quality["empty_text_hits"],
            "agent2_null_score_hits": agent2_quality["null_score_hits"],
            "agent2_fallback_derived_hits": agent2_quality["fallback_derived_hits"],
            "agent2_score_available_hits": agent2_quality["with_score"],
            "agent2_score_missing_hits": agent2_quality["null_score_hits"],
            "agent2_score_source_type_breakdown": agent2_quality["score_source_type_breakdown"],
            "agent2_include_payload_present": agent2_extraction.get("include_payload_present", False),
        },
    )
    rlog.persist()

    evidence = {
        "agent1": agent1_annotations,
        "agent2": agent2_annotations,
    }
    evidence_diagnostics = {
        "agent1": agent1_extraction,
        "agent2": agent2_extraction,
    }

    return {
        "request_id": request_id,
        "markdown_report": markdown,
        "agent2_json": agent2.model_dump(exclude_none=True),
        "agent1_json": agent1.model_dump(),
        "evidence": evidence,
        "evidence_diagnostics": evidence_diagnostics,
        "extracted_frames": extracted_frames_response,
        "timings": rlog.timings,
        "timings_display": format_timings_display(rlog.timings),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enforce_low_confidence(
    agent1: Agent1Output, agent2: Agent2Output, region: str
) -> None:
    low_warning = LOW_CONFIDENCE_WARNING[region]
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

        if bp.open_punten is None:
            bp.open_punten = []
        if low_warning.lower() not in " ".join(bp.open_punten).lower():
            bp.open_punten.append(low_warning)

        cameras_str = ", ".join(low_posts[bp.nummer])
        warning_msg = LOW_CONFIDENCE_MESSAGE[region].format(
            nummer=bp.nummer,
            cameras=cameras_str,
            warning=low_warning,
        )

        if not any(low_warning.lower() in item.lower() and bp.nummer in item for item in agent2.extra_input_nodig):
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


def _preserve_visual_references(agent1: Agent1Output, agent2: Agent2Output) -> None:
    """Keep photo indices and camera labels from Agent 1 as source-of-truth."""
    refs_by_nummer = {
        bp.nummer: {
            "camera_labels": bp.camera_labels,
            "image_indices": bp.image_indices,
        }
        for bp in agent1.bestekposten
    }

    for bp in agent2.bestekposten:
        refs = refs_by_nummer.get(bp.nummer)
        if not refs:
            continue
        if not bp.camera_labels:
            bp.camera_labels = list(refs["camera_labels"])
        if not bp.image_indices:
            bp.image_indices = list(refs["image_indices"])


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
    strict_issues = _find_strict_schema_issues(schema)
    if strict_issues:
        details = "; ".join(strict_issues[:5])
        raise RuntimeError(
            "Invalid Agent 2 strict schema configuration. "
            f"Every object property must be listed in required. Details: {details}"
        )
    return schema


def _build_agent2_instructions(report_fields: set[str], region: str = "flemish") -> str:
    region = normalize_region(region)
    base_prompt = load_region_prompt("agent2", region)
    msgs = KB_MESSAGES[region]
    active_fields = sorted(ALWAYS_REQUIRED_AGENT2_FIELDS | report_fields)
    inactive_fields = sorted(OPTIONAL_AGENT2_FIELDS - report_fields)
    inactive_str = ", ".join(inactive_fields) if inactive_fields else (
        "geen" if region == "flemish" else "aucun"
    )
    return (
        f"{base_prompt}\n\n"
        f"{msgs['agent2_active_fields_header']}\n"
        f"{msgs['agent2_active_fields_body'].format(active=', '.join(active_fields), inactive=inactive_str)}"
    )


def _find_strict_schema_issues(node: object, path: str = "$") -> list[str]:
    issues: list[str] = []
    if not isinstance(node, dict):
        return issues

    if node.get("type") == "object":
        properties = node.get("properties")
        required = node.get("required")
        if isinstance(properties, dict):
            prop_keys = set(properties.keys())
            if not isinstance(required, list):
                issues.append(f"{path}: missing required list")
            else:
                required_keys = set(required)
                missing = sorted(prop_keys - required_keys)
                if missing:
                    issues.append(f"{path}: required missing {missing}")

    properties = node.get("properties")
    if isinstance(properties, dict):
        for key, child in properties.items():
            issues.extend(_find_strict_schema_issues(child, f"{path}.properties.{key}"))

    items = node.get("items")
    if isinstance(items, dict):
        issues.extend(_find_strict_schema_issues(items, f"{path}.items"))

    for branch_key in ("anyOf", "oneOf", "allOf"):
        branches = node.get(branch_key)
        if isinstance(branches, list):
            for idx, branch in enumerate(branches):
                issues.extend(_find_strict_schema_issues(branch, f"{path}.{branch_key}[{idx}]"))

    return issues
