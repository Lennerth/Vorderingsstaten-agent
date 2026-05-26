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
from app.utils.video_processing import extract_frames, validate_video_upload

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
MAX_CAMERAS = MAX_PAIRS
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
    "low": {
        "quality": _parse_int_env("COMPRESSION_PRESET_LOW_QUALITY", 90, min_val=1),
        "target_image_mb": _parse_float_env(
            "COMPRESSION_PRESET_LOW_TARGET_MB", 5.0, min_val=0.001
        ),
    },
    "medium": {"quality": None, "target_image_mb": None},
    "high": {
        "quality": _parse_int_env("COMPRESSION_PRESET_HIGH_QUALITY", 65, min_val=1),
        "target_image_mb": _parse_float_env(
            "COMPRESSION_PRESET_HIGH_TARGET_MB", 1.0, min_val=0.001
        ),
    },
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


def _parse_json_list(raw: str, field_name: str) -> list:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"{field_name} must be a JSON array.") from exc
    if not isinstance(parsed, list):
        raise HTTPException(400, f"{field_name} must be a JSON array.")
    return parsed


def _build_camera_inputs(
    *,
    track_order: list[str],
    pair_labels: list[str],
    video_labels: list[str],
    pair_inputs: list[tuple[bytes, bytes, str, str]],
    video_inputs: list[tuple[bytes, str, str]],
) -> tuple[list[dict], list[dict]]:
    """Build ordered camera_inputs and upload metadata for storage."""
    camera_inputs: list[dict] = []
    uploaded_tracks: list[dict] = []
    pair_idx = 0
    video_idx = 0

    for kind in track_order:
        if kind == "pair":
            if pair_idx >= len(pair_inputs):
                raise HTTPException(400, "track_order references more pair tracks than uploaded.")
            before_bytes, after_bytes, before_name, after_name = pair_inputs[pair_idx]
            label = pair_labels[pair_idx] if pair_idx < len(pair_labels) else f"Camera {pair_idx + 1}"
            camera_inputs.append(
                {
                    "kind": "pair",
                    "camera_label": label,
                    "before_bytes": before_bytes,
                    "after_bytes": after_bytes,
                }
            )
            uploaded_tracks.append(
                {
                    "kind": "pair",
                    "camera_label": label,
                    "before_filename": before_name,
                    "after_filename": after_name,
                }
            )
            pair_idx += 1
        elif kind == "timelapse":
            if video_idx >= len(video_inputs):
                raise HTTPException(400, "track_order references more timelapse tracks than uploaded.")
            video_bytes, video_name, content_type = video_inputs[video_idx]
            label = (
                video_labels[video_idx]
                if video_idx < len(video_labels)
                else f"Camera {video_idx + 1}"
            )
            try:
                extracted = extract_frames(video_bytes)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            frames = [
                {"timestamp_s": frame.timestamp_s, "jpeg_bytes": frame.jpeg_bytes}
                for frame in extracted
            ]
            camera_inputs.append(
                {
                    "kind": "timelapse",
                    "camera_label": label,
                    "frames": frames,
                    "video_filename": video_name,
                    "video_content_type": content_type,
                }
            )
            uploaded_tracks.append(
                {
                    "kind": "timelapse",
                    "camera_label": label,
                    "video_filename": video_name,
                    "frame_count": len(frames),
                    "timestamps": [frame["timestamp_s"] for frame in frames],
                    "frame_jpeg_bytes": [frame["jpeg_bytes"] for frame in frames],
                }
            )
            video_idx += 1
        else:
            raise HTTPException(
                400,
                f"Invalid track kind {kind!r} in track_order (use 'pair' or 'timelapse').",
            )

    if pair_idx != len(pair_inputs) or video_idx != len(video_inputs):
        raise HTTPException(400, "track_order does not match uploaded pair/video counts.")

    return camera_inputs, uploaded_tracks


@router.get("/config")
async def public_config():
    """Expose server limits to the UI."""
    return {
        "max_cameras": MAX_CAMERAS,
        "max_image_mb": MAX_IMAGE_MB,
        "max_total_mb": MAX_TOTAL_MB,
    }


@router.post("/progress-report")
async def progress_report(
    before_images: list[UploadFile] = File(default=[]),
    after_images: list[UploadFile] = File(default=[]),
    camera_labels: str = Form("[]"),
    videos: list[UploadFile] = File(default=[]),
    video_labels: str = Form("[]"),
    track_order: str = Form("[]"),
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
    n_videos = len(videos)

    if n_pairs != len(after_images):
        raise HTTPException(400, "Number of before and after images must match.")

    parsed_track_order = _parse_json_list(track_order, "track_order")
    if parsed_track_order:
        if not all(kind in ("pair", "timelapse") for kind in parsed_track_order):
            raise HTTPException(
                400,
                "track_order entries must be 'pair' or 'timelapse'.",
            )
        if parsed_track_order.count("pair") != n_pairs:
            raise HTTPException(400, "track_order pair count must match before_images count.")
        if parsed_track_order.count("timelapse") != n_videos:
            raise HTTPException(400, "track_order timelapse count must match videos count.")
        order = [str(kind) for kind in parsed_track_order]
    else:
        order = ["pair"] * n_pairs + ["timelapse"] * n_videos

    n_tracks = len(order)
    if n_tracks == 0:
        raise HTTPException(400, "At least one camera track (pair or timelapse) is required.")
    if n_tracks > MAX_CAMERAS:
        raise HTTPException(
            400,
            f"Number of camera tracks must be between 1 and {MAX_CAMERAS}.",
        )

    logger.info(
        "[%s] Incoming request: %d pair(s), %d timelapse(s), region=%s",
        request_id,
        n_pairs,
        n_videos,
        region,
    )

    ok, resources = check_resources()
    if not ok:
        logger.warning(
            "[%s] Insufficient resources (track_count=%d): %s",
            request_id,
            n_tracks,
            resources,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Server resources insufficient – "
                f"RAM free: {resources['ram_percent_free']:.1f}%, "
                f"CPU: {resources['cpu_percent']:.1f}%"
            ),
        )

    parsed_pair_labels = _parse_json_list(camera_labels, "camera_labels")
    if parsed_pair_labels and len(parsed_pair_labels) != n_pairs:
        raise HTTPException(
            400,
            "camera_labels length must match the number of image pairs.",
        )
    pair_labels = [str(label) for label in parsed_pair_labels] if parsed_pair_labels else [
        f"Camera {i + 1}" for i in range(n_pairs)
    ]

    parsed_video_labels = _parse_json_list(video_labels, "video_labels")
    if parsed_video_labels and len(parsed_video_labels) != n_videos:
        raise HTTPException(
            400,
            "video_labels length must match the number of videos.",
        )
    video_label_list = (
        [str(label) for label in parsed_video_labels]
        if parsed_video_labels
        else [f"Camera {n_pairs + i + 1}" for i in range(n_videos)]
    )

    all_labels = []
    pair_label_iter = iter(pair_labels)
    video_label_iter = iter(video_label_list)
    for kind in order:
        label = next(pair_label_iter if kind == "pair" else video_label_iter)
        all_labels.append(label)
    if len(set(all_labels)) != len(all_labels):
        raise HTTPException(400, "Camera labels must be unique across all tracks.")

    bestekpost_filters = [
        item.strip()
        for item in bestekpost_filter.split(",")
        if item.strip()
    ] or None

    if report_fields.strip():
        parsed_report_fields = json.loads(report_fields)
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

    pair_inputs: list[tuple[bytes, bytes, str, str]] = []
    video_inputs: list[tuple[bytes, str, str]] = []
    total_size = 0

    for i in range(n_pairs):
        before = before_images[i]
        after = after_images[i]
        before_bytes = await before.read()
        after_bytes = await after.read()

        if not before_bytes or not after_bytes:
            raise HTTPException(400, f"Empty file detected in pair {i + 1}.")

        if len(before_bytes) > MAX_IMAGE_SIZE or len(after_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(
                400,
                f"Image in pair {i + 1} exceeds max size of {MAX_IMAGE_MB:g} MB.",
            )

        total_size += len(before_bytes) + len(after_bytes)
        pair_inputs.append(
            (
                before_bytes,
                after_bytes,
                before.filename or f"camera_{i + 1}_before",
                after.filename or f"camera_{i + 1}_after",
            )
        )

    for i, video in enumerate(videos):
        video_bytes = await video.read()
        if not video_bytes:
            raise HTTPException(400, f"Empty video detected in timelapse track {i + 1}.")
        try:
            validate_video_upload(
                video.filename or f"camera_{i + 1}.mp4",
                video.content_type or "video/mp4",
                len(video_bytes),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        total_size += len(video_bytes)
        video_inputs.append(
            (
                video_bytes,
                video.filename or f"camera_{i + 1}.mp4",
                video.content_type or "video/mp4",
            )
        )

    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            400,
            f"Total upload size exceeds max size of {MAX_TOTAL_MB:g} MB.",
        )

    camera_inputs, uploaded_tracks = _build_camera_inputs(
        track_order=order,
        pair_labels=pair_labels,
        video_labels=video_label_list,
        pair_inputs=pair_inputs,
        video_inputs=video_inputs,
    )

    try:
        result = await run_pipeline(
            camera_inputs,
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
            uploaded_tracks,
            report_fields=selected_report_fields,
            bestekpost_filters=bestekpost_filters or [],
            region=region,
        )
        logger.info("[%s] Output artifacts saved to %s", request_id, output_dir)
    except Exception:
        logger.exception("[%s] Failed to store output artifacts", request_id)
        raise HTTPException(500, "Report generated but storing output files failed.")

    return result
