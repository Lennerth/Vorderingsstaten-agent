"""FastAPI router with the POST /progress-report endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.logging_utils import generate_request_id
from app.orchestrator import run_pipeline
from app.utils.system_monitor import check_resources

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB per image


@router.post("/progress-report")
async def progress_report(
    before: UploadFile = File(..., description="Foto voor (eerder)"),
    after: UploadFile = File(..., description="Foto na (later)"),
):
    request_id = generate_request_id()
    logger.info(
        "[%s] Incoming request  before=%s  after=%s",
        request_id,
        before.filename,
        after.filename,
    )

    ok, resources = check_resources()
    if not ok:
        logger.warning("[%s] Insufficient resources: %s", request_id, resources)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Server resources insufficient – "
                f"RAM free: {resources['ram_percent_free']:.1f}%, "
                f"CPU: {resources['cpu_percent']:.1f}%"
            ),
        )

    before_bytes = await before.read()
    after_bytes = await after.read()

    if not before_bytes or not after_bytes:
        raise HTTPException(400, "Both before and after images are required.")

    if len(before_bytes) > MAX_IMAGE_SIZE or len(after_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            400,
            f"Image exceeds max size of {MAX_IMAGE_SIZE // (1024 * 1024)} MB.",
        )

    try:
        result = await run_pipeline(before_bytes, after_bytes, request_id)
    except Exception:
        logger.exception("[%s] Pipeline failed", request_id)
        raise HTTPException(500, "Internal pipeline error – see server logs.")

    return result
