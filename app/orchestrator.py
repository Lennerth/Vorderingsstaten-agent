"""Pipeline: image optimization → Agent 1 → Agent 2 → markdown."""

from __future__ import annotations

import asyncio
import logging
import time

from app.kb import run_agent1, run_agent2
from app.logging_utils import RequestLogger
from app.models import Agent1Output, Agent2Output
from app.reporting import render_markdown
from app.utils.image_processing import optimize_and_encode

logger = logging.getLogger(__name__)

async def run_pipeline(
    camera_pairs: list[dict],
    request_id: str,
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
    agent1_raw, agent1_annotations = await run_agent1(images)
    rlog.log_step("agent1_raw_output", {"output": agent1_raw})

    try:
        agent1 = Agent1Output.model_validate(agent1_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 1 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent1_retry", {"error": str(exc)})
        agent1_raw, agent1_annotations = await run_agent1(images)
        agent1 = Agent1Output.model_validate(agent1_raw)

    rlog.add_timing("agent1", time.time() - t1)
    total_posts = len(agent1.bestekposten)
    logger.info("[%s] Agent 1 returned %d bestekposten", request_id, total_posts)

    # ── 3. Detail retrieval (via Agent 2 internal tool use) ────────────────
    # We skip explicit parallel retrieval because Azure doesn't support
    # client.vector_stores.search() directly. We let Agent 2 do it.

    # ── 4. Agent 2: enrichment ───────────────────────────────────────────
    logger.info("[%s] Running Agent 2 (with file_search) …", request_id)
    t3 = time.time()
    agent2_raw = await run_agent2(agent1_raw)
    rlog.log_step("agent2_raw_output", {"output": agent2_raw})

    try:
        agent2 = Agent2Output.model_validate(agent2_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 2 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent2_retry", {"error": str(exc)})
        agent2_raw = await run_agent2(agent1_raw)
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
        "agent2_json": agent2.model_dump(),
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
            
        if _LOW_WARNING.lower() not in " ".join(bp.open_punten).lower():
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
            for label in bp.camera_labels:
                if label not in existing.camera_labels:
                    existing.camera_labels.append(label)
            for idx in bp.image_indices:
                if idx not in existing.image_indices:
                    existing.image_indices.append(idx)
            
            for point in bp.open_punten:
                if point not in existing.open_punten:
                    existing.open_punten.append(point)
                    
    agent2.bestekposten = list(merged.values())
    agent2.bestekposten.sort(key=lambda x: x.nummer)
