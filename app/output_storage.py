"""Persist generated report artifacts into incremented output folders."""

from __future__ import annotations

import json
from pathlib import Path


def save_report_output(result: dict, uploaded_images: list[dict]) -> Path:
    """Save markdown, uploaded filenames, and JSON output for one request."""
    outputs_root = Path("outputs")
    output_dir = _create_next_output_dir(outputs_root)

    markdown_report = str(result.get("markdown_report", ""))
    (output_dir / "report.md").write_text(markdown_report, encoding="utf-8")

    image_lines = [
        "Uploaded images used for report generation",
        "",
    ]
    for image_info in uploaded_images:
        camera_label = image_info.get("camera_label", "Camera")
        before_name = image_info.get("before_filename", "(unknown before image)")
        after_name = image_info.get("after_filename", "(unknown after image)")
        image_lines.append(f"{camera_label}:")
        image_lines.append(f"- before: {before_name}")
        image_lines.append(f"- after: {after_name}")
        image_lines.append("")
    (output_dir / "uploaded_images.txt").write_text(
        "\n".join(image_lines).rstrip() + "\n",
        encoding="utf-8",
    )

    (output_dir / "output.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_dir


def _create_next_output_dir(outputs_root: Path) -> Path:
    outputs_root.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        dir_name = f"output {_number_to_words(index)}"
        candidate = outputs_root / dir_name
        try:
            candidate.mkdir(parents=False, exist_ok=False)
            return candidate
        except FileExistsError:
            index += 1


def _number_to_words(number: int) -> str:
    if number <= 0:
        raise ValueError("number must be a positive integer")

    ones = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
    }
    teens = {
        10: "ten",
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
        19: "nineteen",
    }
    tens = {
        2: "twenty",
        3: "thirty",
        4: "forty",
        5: "fifty",
        6: "sixty",
        7: "seventy",
        8: "eighty",
        9: "ninety",
    }

    if number < 10:
        return ones[number]
    if number < 20:
        return teens[number]
    if number < 100:
        ten_digit, remainder = divmod(number, 10)
        return tens[ten_digit] if remainder == 0 else f"{tens[ten_digit]} {ones[remainder]}"
    if number < 1000:
        hundred_digit, remainder = divmod(number, 100)
        prefix = f"{ones[hundred_digit]} hundred"
        return prefix if remainder == 0 else f"{prefix} {_number_to_words(remainder)}"
    if number < 1_000_000:
        thousand_digit, remainder = divmod(number, 1000)
        prefix = f"{_number_to_words(thousand_digit)} thousand"
        return prefix if remainder == 0 else f"{prefix} {_number_to_words(remainder)}"
    if number < 1_000_000_000:
        million_digit, remainder = divmod(number, 1_000_000)
        prefix = f"{_number_to_words(million_digit)} million"
        return prefix if remainder == 0 else f"{prefix} {_number_to_words(remainder)}"

    billion_digit, remainder = divmod(number, 1_000_000_000)
    prefix = f"{_number_to_words(billion_digit)} billion"
    return prefix if remainder == 0 else f"{prefix} {_number_to_words(remainder)}"
