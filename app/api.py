"""FastAPI router with the POST /progress-report endpoint."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.logging_utils import generate_request_id
from app.output_storage import save_report_output
from app.orchestrator import InvalidBestekpostFilter, run_pipeline
from app.regions import normalize_region
from app.utils.system_monitor import check_resources

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB per image
MAX_TOTAL_SIZE = 120 * 1024 * 1024 # 120 MB total
MAX_PAIRS = 6
ALLOWED_REPORT_FIELDS = {
    "zichtbaar_uitgevoerd",
    "bestekeisen",
    "bron",
    "image_indices",
    "camera_labels",
    "open_punten",
    "volgende_stap",
}


@router.post("/progress-report")
async def progress_report(
    before_images: list[UploadFile] = File(...),
    after_images: list[UploadFile] = File(...),
    camera_labels: str = Form("[]"),
    bestekpost_filter: str = Form(""),
    report_fields: str = Form(""),
    region: str = Form("flemish"),
):
    request_id = generate_request_id()

    try:
        region = normalize_region(region)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    
    n_pairs = len(before_images)
    logger.info(
        "[%s] Incoming request: %d pairs, region=%s",
        request_id,
        n_pairs,
        region,
    )

    if n_pairs != len(after_images):
        raise HTTPException(400, "Number of before and after images must match.")

    if not (1 <= n_pairs <= MAX_PAIRS):
        raise HTTPException(400, f"Number of pairs must be between 1 and {MAX_PAIRS}.")

    ok, resources = check_resources()
    if not ok:
        logger.warning("[%s] Insufficient resources (pair_count=%d): %s", request_id, n_pairs, resources)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Server resources insufficient – "
                f"RAM free: {resources['ram_percent_free']:.1f}%, "
                f"CPU: {resources['cpu_percent']:.1f}%"
            ),
        )

    try:
        parsed_labels = json.loads(camera_labels)
        if not isinstance(parsed_labels, list) or len(parsed_labels) != n_pairs:
            raise ValueError()
        labels = [str(l) for l in parsed_labels]
    except Exception:
        labels = [f"Camera {i+1}" for i in range(n_pairs)]

    bestekpost_filters = [
        item.strip()
        for item in bestekpost_filter.split(",")
        if item.strip()
    ] or None

    if report_fields.strip():
        try:
            parsed_report_fields = json.loads(report_fields)
        except json.JSONDecodeError:
            raise HTTPException(400, "report_fields must be a JSON array.")
        if not isinstance(parsed_report_fields, list) or not all(
            isinstance(field, str) for field in parsed_report_fields
        ):
            raise HTTPException(400, "report_fields must be a JSON array of strings.")
        invalid_fields = sorted(set(parsed_report_fields) - ALLOWED_REPORT_FIELDS)
        if invalid_fields:
            raise HTTPException(
                400,
                f"Invalid report_fields: {', '.join(invalid_fields)}.",
            )
        selected_report_fields = parsed_report_fields
    else:
        selected_report_fields = sorted(ALLOWED_REPORT_FIELDS)

    camera_pairs = []
    uploaded_image_names = []
    total_size = 0

    for i in range(n_pairs):
        before = before_images[i]
        after = after_images[i]

        before_bytes = await before.read()
        after_bytes = await after.read()

        if not before_bytes or not after_bytes:
            raise HTTPException(400, f"Empty file detected in pair {i+1}.")

        if len(before_bytes) > MAX_IMAGE_SIZE or len(after_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(
                400,
                f"Image in pair {i+1} exceeds max size of {MAX_IMAGE_SIZE // (1024 * 1024)} MB.",
            )

        total_size += len(before_bytes) + len(after_bytes)

        camera_pairs.append({
            "camera_label": labels[i],
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
        })
        uploaded_image_names.append(
            {
                "camera_label": labels[i],
                "before_filename": before.filename or f"camera_{i + 1}_before",
                "after_filename": after.filename or f"camera_{i + 1}_after",
            }
        )

    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            400,
            f"Total upload size exceeds max size of {MAX_TOTAL_SIZE // (1024 * 1024)} MB."
        )

    try:
        result = await run_pipeline(
            camera_pairs,
            request_id,
            bestekpost_filter=bestekpost_filters,
            report_fields=selected_report_fields,
            region=region,
        )
    except InvalidBestekpostFilter as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        logger.exception("[%s] Pipeline failed", request_id)
        raise HTTPException(500, "Internal pipeline error – see server logs.")

    try:
        output_dir = save_report_output(
            result,
            uploaded_image_names,
            report_fields=selected_report_fields,
            bestekpost_filters=bestekpost_filters or [],
            region=region,
        )
        logger.info("[%s] Output artifacts saved to %s", request_id, output_dir)
    except Exception:
        logger.exception("[%s] Failed to store output artifacts", request_id)
        raise HTTPException(500, "Report generated but storing output files failed.")

    return result
