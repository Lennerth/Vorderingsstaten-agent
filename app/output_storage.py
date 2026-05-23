"""Persist generated report artifacts into incremented output folders."""

from __future__ import annotations

import json
from pathlib import Path

from app.regions import OUTPUT_STORAGE_LABELS, normalize_region


def save_report_output(
    result: dict,
    uploaded_images: list[dict],
    report_fields: list[str],
    bestekpost_filters: list[str],
    region: str = "flemish",
) -> Path:
    """Save markdown, uploaded filenames, and JSON output for one request."""
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
    for image_info in uploaded_images:
        camera_label = image_info.get("camera_label", labels["camera_fallback"])
        before_name = image_info.get("before_filename", labels["unknown_before"])
        after_name = image_info.get("after_filename", labels["unknown_after"])
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

    (output_dir / "output.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    evidence = result.get("evidence")
    if evidence is not None:
        (output_dir / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return output_dir


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
