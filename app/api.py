"""FastAPI router with the POST /progress-report endpoint."""

from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.logging_utils import generate_request_id
from app.output_storage import save_report_output
from app.orchestrator import InvalidBestekpostFilter, run_pipeline
from app.regions import normalize_region
from app.utils.system_monitor import check_resources

logger = logging.getLogger(__name__)

router = APIRouter()

_UPLOAD_DEFAULTS = {
    "max_image_mb": 20,
    "max_total_mb": 120,
    "max_pairs": 6,
}
_warned: set[str] = set()


def _warn_once(key: str, msg: str) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg)


def _parse_int_env(
    name: str,
    default: int,
    *,
    min_val: int | None = None,
) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _warn_once(name, f"{name}={raw!r} is not a valid integer; using default {default}")
        return default
    if min_val is not None and value < min_val:
        _warn_once(
            name,
            f"{name}={value} is below minimum {min_val}; using default {default}",
        )
        return default
    return value


def _parse_float_env(
    name: str,
    default: float,
    *,
    min_val: float | None = None,
) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        _warn_once(name, f"{name}={raw!r} is not a valid number; using default {default}")
        return default
    if min_val is not None and value < min_val:
        _warn_once(
            name,
            f"{name}={value} is below minimum {min_val}; using default {default}",
        )
        return default
    return value


MAX_IMAGE_MB = _parse_float_env(
    "UPLOAD_MAX_IMAGE_MB",
    _UPLOAD_DEFAULTS["max_image_mb"],
    min_val=0.001,
)
MAX_TOTAL_MB = _parse_float_env(
    "UPLOAD_MAX_TOTAL_MB",
    _UPLOAD_DEFAULTS["max_total_mb"],
    min_val=0.001,
)
MAX_PAIRS = _parse_int_env(
    "UPLOAD_MAX_PAIRS",
    _UPLOAD_DEFAULTS["max_pairs"],
    min_val=1,
)
MAX_IMAGE_SIZE = int(MAX_IMAGE_MB * 1024 * 1024)
MAX_TOTAL_SIZE = int(MAX_TOTAL_MB * 1024 * 1024)
ALLOWED_REPORT_FIELDS = {
    "zichtbaar_uitgevoerd",
    "bestekeisen",
    "bron",
    "image_indices",
    "camera_labels",
    "open_punten",
    "volgende_stap",
}

VALID_COMPRESSION_PRESETS = {"low", "medium", "high"}
MIN_JPEG_QUALITY = 1
MAX_JPEG_QUALITY = 95
MIN_TARGET_IMAGE_MB = 0.2
MAX_TARGET_IMAGE_MB = 10.0

PRESET_COMPRESSION = {
    "low": {"quality": 90, "target_image_mb": 5.0},
    "medium": {"quality": None, "target_image_mb": None},
    "high": {"quality": 65, "target_image_mb": 1.0},
}


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_compression_options(
    compression_preset: str = "medium",
    compression_advanced: str = "",
    jpeg_quality: str = "",
    target_image_mb: str = "",
) -> dict:
    if _truthy(compression_advanced):
        if not jpeg_quality.strip():
            raise HTTPException(400, "jpeg_quality is required when compression_advanced is enabled.")
        if not target_image_mb.strip():
            raise HTTPException(400, "target_image_mb is required when compression_advanced is enabled.")
        try:
            quality = int(jpeg_quality.strip())
        except ValueError:
            raise HTTPException(400, "jpeg_quality must be an integer between 1 and 95.")
        if not (MIN_JPEG_QUALITY <= quality <= MAX_JPEG_QUALITY):
            raise HTTPException(
                400,
                f"jpeg_quality must be between {MIN_JPEG_QUALITY} and {MAX_JPEG_QUALITY}.",
            )
        try:
            target_mb = float(target_image_mb.strip())
        except ValueError:
            raise HTTPException(400, "target_image_mb must be a number.")
        if not (MIN_TARGET_IMAGE_MB <= target_mb <= MAX_TARGET_IMAGE_MB):
            raise HTTPException(
                400,
                f"target_image_mb must be between {MIN_TARGET_IMAGE_MB:g} and {MAX_TARGET_IMAGE_MB:g}.",
            )
        return {
            "mode": "advanced",
            "preset": None,
            "quality": quality,
            "target_image_mb": target_mb,
        }

    preset = (compression_preset or "medium").strip().lower()
    if preset not in VALID_COMPRESSION_PRESETS:
        raise HTTPException(
            400,
            f"compression_preset must be one of: {', '.join(sorted(VALID_COMPRESSION_PRESETS))}.",
        )

    settings = PRESET_COMPRESSION[preset]
    if preset == "medium":
        return {
            "mode": "default",
            "preset": preset,
            "quality": None,
            "target_image_mb": None,
        }
    return {
        "mode": "preset",
        "preset": preset,
        "quality": settings["quality"],
        "target_image_mb": settings["target_image_mb"],
    }


@router.post("/progress-report")
async def progress_report(
    before_images: list[UploadFile] = File(...),
    after_images: list[UploadFile] = File(...),
    camera_labels: str = Form("[]"),
    bestekpost_filter: str = Form(""),
    report_fields: str = Form(""),
    region: str = Form("flemish"),
    compression_preset: str = Form("medium"),
    compression_advanced: str = Form(""),
    jpeg_quality: str = Form(""),
    target_image_mb: str = Form(""),
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

    compression_options = parse_compression_options(
        compression_preset=compression_preset,
        compression_advanced=compression_advanced,
        jpeg_quality=jpeg_quality,
        target_image_mb=target_image_mb,
    )
    logger.info(
        "[%s] Compression options: mode=%s preset=%s quality=%s target_image_mb=%s",
        request_id,
        compression_options["mode"],
        compression_options.get("preset"),
        compression_options.get("quality"),
        compression_options.get("target_image_mb"),
    )

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
                f"Image in pair {i+1} exceeds max size of {MAX_IMAGE_MB:g} MB.",
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
            f"Total upload size exceeds max size of {MAX_TOTAL_MB:g} MB."
        )

    try:
        result = await run_pipeline(
            camera_pairs,
            request_id,
            bestekpost_filter=bestekpost_filters,
            report_fields=selected_report_fields,
            region=region,
            compression_options=compression_options,
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
