"""Pipeline: image optimization → Agent 1 → parallel detail retrieval → Agent 2 → markdown."""

from __future__ import annotations

import asyncio
import logging
import time

from app.kb import run_agent1, run_agent2, search_details
from app.logging_utils import RequestLogger
from app.models import Agent1Output, Agent2Output, RetrievalLogEntry
from app.reporting import render_markdown
from app.utils.image_processing import optimize_and_encode
from app.utils.system_monitor import get_safe_concurrency

logger = logging.getLogger(__name__)


def determine_deel(bestekpostnummer: str) -> int:
    """'30.14' → first two digits 30 → 30 // 10 = 3."""
    return int(bestekpostnummer[:2]) // 10


async def run_pipeline(
    before_bytes: bytes,
    after_bytes: bytes,
    request_id: str,
) -> dict:
    rlog = RequestLogger(request_id)
    t_start = time.time()

    # ── 1. Image optimisation ────────────────────────────────────────────
    logger.info("[%s] Optimizing images …", request_id)
    before_url, before_size = optimize_and_encode(before_bytes)
    after_url, after_size = optimize_and_encode(after_bytes)
    rlog.log_step("image_optimization", {"before": before_size, "after": after_size})
    rlog.add_timing("image_optimization", time.time() - t_start)

    # ── 2. Agent 1: vision + master file_search ──────────────────────────
    logger.info("[%s] Running Agent 1 …", request_id)
    t1 = time.time()
    agent1_raw, agent1_annotations = await run_agent1(before_url, after_url)
    rlog.log_step("agent1_raw_output", {"output": agent1_raw})

    try:
        agent1 = Agent1Output.model_validate(agent1_raw)
    except Exception as exc:
        logger.warning("[%s] Agent 1 validation failed (%s), retrying …", request_id, exc)
        rlog.log_step("agent1_retry", {"error": str(exc)})
        agent1_raw, agent1_annotations = await run_agent1(before_url, after_url)
        agent1 = Agent1Output.model_validate(agent1_raw)

    rlog.add_timing("agent1", time.time() - t1)
    total_posts = sum(len(t.bestekpostnummers) for t in agent1.transitions)
    logger.info("[%s] Agent 1 returned %d bestekpostnummers", request_id, total_posts)

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
    rlog.add_timing("agent2", time.time() - t3)

    # ── 5. Render markdown ───────────────────────────────────────────────
    markdown = render_markdown(agent2)

    total_time = time.time() - t_start
    rlog.add_timing("total", total_time)
    logger.info("[%s] Pipeline complete in %.1f s", request_id, total_time)

    rlog.log_step("pipeline_complete", {"total_s": round(total_time, 2)})
    rlog.persist()

    return {
        "markdown_report": markdown,
        "agent2_json": agent2.model_dump(),
        "agent1_json": agent1.model_dump(),
        "retrieval_log": [],  # Empty because retrieval is now internal to Agent 2
    }


# ---------------------------------------------------------------------------
# MVP rule: force warning when Agent 1 confidence is low
# ---------------------------------------------------------------------------

_LOW_WARNING = "Manuele check / extra foto nodig"


def _enforce_low_confidence(agent1: Agent1Output, agent2: Agent2Output) -> None:
    low_transitions = {
        (t.from_photo, t.to_photo)
        for t in agent1.transitions
        if t.zekerheid == "laag"
    }
    if not low_transitions:
        return

    for tr in agent2.transitions:
        if (tr.from_photo, tr.to_photo) not in low_transitions:
            continue
        for bp in tr.bestekposten:
            if _LOW_WARNING.lower() not in " ".join(bp.open_punten).lower():
                bp.open_punten.append(_LOW_WARNING)
        if not any(_LOW_WARNING.lower() in item.lower() for item in agent2.extra_input_nodig):
            agent2.extra_input_nodig.append(
                f"Overgang Foto {tr.from_photo} → {tr.to_photo}: {_LOW_WARNING}"
            )
