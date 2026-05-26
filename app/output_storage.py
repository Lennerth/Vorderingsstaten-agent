"""Persist generated report artifacts into incremented output folders."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.regions import OUTPUT_STORAGE_LABELS, normalize_region


def save_report_output(
    result: dict,
    uploaded_tracks: list[dict],
    report_fields: list[str],
    bestekpost_filters: list[str],
    region: str = "flemish",
) -> Path:
    """Save markdown, uploaded filenames, extracted frames, and JSON output."""
    region = normalize_region(region)
    labels = OUTPUT_STORAGE_LABELS[region]
    outputs_root = Path("outputs")
    output_dir = _create_next_output_dir(outputs_root)

    markdown_report = str(result.get("markdown_report", ""))
    (output_dir / "report.md").write_text(markdown_report, encoding="utf-8")

    image_lines = [
        labels["uploaded_images_title"],
        "",
    ]
    for track in uploaded_tracks:
        camera_label = track.get("camera_label", labels["camera_fallback"])
        kind = track.get("kind", "pair")
        if kind == "timelapse":
            video_name = track.get("video_filename", labels["unknown_video"])
            timestamps = track.get("timestamps") or []
            frame_count = track.get("frame_count", len(timestamps))
            ts_summary = ", ".join(f"{ts:g}s" for ts in timestamps)
            image_lines.append(f"{camera_label} ({labels['timelapse']}):")
            image_lines.append(f"- {labels['timelapse_video']}: {video_name}")
            image_lines.append(
                f"- {labels['timelapse_frames']}: {frame_count} ({ts_summary})"
            )
            _save_timelapse_frames(output_dir, track)
        else:
            before_name = track.get("before_filename", labels["unknown_before"])
            after_name = track.get("after_filename", labels["unknown_after"])
            image_lines.append(f"{camera_label}:")
            image_lines.append(f"- {labels['before']}: {before_name}")
            image_lines.append(f"- {labels['after']}: {after_name}")
        image_lines.append("")

    (output_dir / "uploaded_images.txt").write_text(
        "\n".join(image_lines).rstrip() + "\n",
        encoding="utf-8",
    )

    options_lines = [
        labels["options_title"],
        "",
        f"{labels['region']}: {region}",
        "",
        f"{labels['report_fields']}:",
    ]
    if report_fields:
        options_lines.extend(f"- {field}" for field in report_fields)
    else:
        options_lines.append(f"- {labels['none_selected']}")

    options_lines.extend(["", f"{labels['bestekpost_filter']}:"])
    if bestekpost_filters:
        options_lines.extend(f"- {filter_value}" for filter_value in bestekpost_filters)
    else:
        options_lines.append(f"- {labels['none']}")

    (output_dir / "request_options.txt").write_text(
        "\n".join(options_lines).rstrip() + "\n",
        encoding="utf-8",
    )

    serializable_result = dict(result)
    (output_dir / "output.json").write_text(
        json.dumps(serializable_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    evidence = result.get("evidence")
    if evidence is not None:
        (output_dir / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return output_dir


def _save_timelapse_frames(output_dir: Path, track: dict) -> None:
    camera_label = track.get("camera_label", "camera")
    safe_label = _safe_dir_name(camera_label)
    frames_dir = output_dir / "frames" / safe_label
    frames_dir.mkdir(parents=True, exist_ok=True)

    timestamps = track.get("timestamps") or []
    frame_bytes = track.get("frame_jpeg_bytes") or []
    for index, (timestamp_s, jpeg_bytes) in enumerate(
        zip(timestamps, frame_bytes), start=1
    ):
        filename = f"frame_{index:02d}_t{timestamp_s:g}.jpg"
        (frames_dir / filename).write_bytes(jpeg_bytes)


def _safe_dir_name(value: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "_", value.strip())
    return cleaned.replace(" ", "_") or "camera"


def _create_next_output_dir(outputs_root: Path) -> Path:
    outputs_root.mkdir(parents=True, exist_ok=True)
    existing_indices = [
        index
        for path in outputs_root.iterdir()
        if path.is_dir() and (index := _output_index_from_name(path.name)) is not None
    ]
    index = max(existing_indices, default=0) + 1
    while True:
        dir_name = f"output {index:02d}"
        candidate = outputs_root / dir_name
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return candidate
        except FileExistsError:
            index += 1


def _output_index_from_name(name: str) -> int | None:
    if not name.startswith("output "):
        return None

    suffix = name.removeprefix("output ").strip().lower()
    if suffix.isdigit():
        return int(suffix)

    legacy_names = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    return legacy_names.get(suffix)
