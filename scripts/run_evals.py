"""
Run evaluation cases against the production pipeline.

Usage:
    python -m scripts.run_evals --region both
    python -m scripts.run_evals --list-cases
    python -m scripts.run_evals --region flemish --dry-run
    python -m scripts.run_evals --region walloon --case tower_cam1_jan_feb --limit 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = PROJECT_ROOT / "evals" / "cases"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evals" / "results"


def _discover_cases(case_filter: list[str] | None) -> list[tuple[str, Path]]:
    if not CASES_DIR.is_dir():
        return []
    cases: list[tuple[str, Path]] = []
    for path in sorted(CASES_DIR.iterdir()):
        if not path.is_dir():
            continue
        case_file = path / "case.json"
        if not case_file.is_file():
            continue
        case_id = path.name
        if case_filter and case_id not in case_filter:
            continue
        cases.append((case_id, case_file))
    return cases


def _load_case(case_path: Path) -> dict:
    return json.loads(case_path.read_text(encoding="utf-8"))


def _validate_case_schema(case_id: str, case: dict) -> list[str]:
    errors: list[str] = []
    if "pairs" not in case or not isinstance(case["pairs"], list) or not case["pairs"]:
        errors.append(f"Case '{case_id}': missing or empty 'pairs'.")
    if "expected" not in case or not isinstance(case["expected"], dict):
        errors.append(f"Case '{case_id}': missing 'expected' object.")
    labels = case.get("camera_labels")
    pairs = case.get("pairs", [])
    if isinstance(labels, list) and len(labels) != len(pairs):
        errors.append(
            f"Case '{case_id}': camera_labels length ({len(labels)}) "
            f"does not match pairs ({len(pairs)})."
        )
    return errors


def _check_image_paths(case_id: str, case: dict) -> list[str]:
    errors: list[str] = []
    for pair in case.get("pairs", []):
        for role in ("before", "after"):
            rel = pair.get(role)
            if not rel:
                errors.append(f"Case '{case_id}': pair missing '{role}' path.")
                continue
            full = PROJECT_ROOT / rel
            if not full.is_file():
                errors.append(
                    f"Case '{case_id}': image not found at '{rel}'"
                )
    return errors


def _regions_for_case(case: dict, region_arg: str) -> list[str]:
    expected = case.get("expected", {})
    if region_arg == "both":
        return [r for r in ("flemish", "walloon") if r in expected]
    if region_arg in expected:
        return [region_arg]
    return [region_arg]


def _nummer_matches_prefix(nummer: str, prefix: str) -> bool:
    return nummer.startswith(prefix)


def _collect_text(agent1_json: dict, agent2_json: dict) -> str:
    parts: list[str] = []
    for bp in agent1_json.get("bestekposten", []):
        for obs in bp.get("observaties", []) or []:
            parts.append(str(obs))
    for bp in agent2_json.get("bestekposten", []):
        for item in bp.get("zichtbaar_uitgevoerd", []) or []:
            parts.append(str(item))
    return " ".join(parts).lower()


def _evaluate_assertions(
    agent1_json: dict,
    agent2_json: dict,
    expected: dict,
) -> tuple[bool, list[dict]]:
    nummers = [
        str(bp.get("nummer", ""))
        for bp in agent2_json.get("bestekposten", [])
    ]
    text_blob = _collect_text(agent1_json, agent2_json)
    assertions: list[dict] = []
    all_passed = True

    for prefix in expected.get("required_prefixes", []):
        passed = any(_nummer_matches_prefix(n, prefix) for n in nummers)
        assertions.append({
            "type": "required_prefix",
            "value": prefix,
            "passed": passed,
            "message": (
                f"At least one bestekpost must start with '{prefix}'"
                if not passed
                else f"Found prefix '{prefix}'"
            ),
        })
        all_passed = all_passed and passed

    for prefix in expected.get("forbidden_prefixes", []):
        matches = [n for n in nummers if _nummer_matches_prefix(n, prefix)]
        passed = len(matches) == 0
        assertions.append({
            "type": "forbidden_prefix",
            "value": prefix,
            "passed": passed,
            "message": (
                f"No bestekpost may start with '{prefix}' (found: {matches})"
                if not passed
                else f"No forbidden prefix '{prefix}'"
            ),
        })
        all_passed = all_passed and passed

    for keyword in expected.get("required_keywords", []):
        passed = keyword.lower() in text_blob
        assertions.append({
            "type": "required_keyword",
            "value": keyword,
            "passed": passed,
            "message": (
                f"Keyword '{keyword}' must appear in observations/uitgevoerd"
                if not passed
                else f"Found keyword '{keyword}'"
            ),
        })
        all_passed = all_passed and passed

    return all_passed, assertions


def _build_camera_pairs(case: dict) -> list[dict]:
    labels = case.get("camera_labels") or []
    pairs = case["pairs"]
    camera_pairs = []
    for i, pair in enumerate(pairs):
        label = labels[i] if i < len(labels) else f"Camera {i + 1}"
        before_path = PROJECT_ROOT / pair["before"]
        after_path = PROJECT_ROOT / pair["after"]
        camera_pairs.append({
            "camera_label": label,
            "before_bytes": before_path.read_bytes(),
            "after_bytes": after_path.read_bytes(),
        })
    return camera_pairs


def _list_cases(case_filter: list[str] | None) -> int:
    cases = _discover_cases(case_filter)
    if not cases:
        print("No evaluation cases found.")
        return 1
    for case_id, case_path in cases:
        case = _load_case(case_path)
        regions = list(case.get("expected", {}).keys())
        print(
            f"{case_id}: {case.get('description', '(no description)')} "
            f"— {len(case.get('pairs', []))} pair(s), regions: {', '.join(regions)}"
        )
    return 0


async def _run_case_region(
    case_id: str,
    case: dict,
    region: str,
    dry_run: bool,
) -> dict:
    from app.logging_utils import generate_request_id
    from app.orchestrator import run_pipeline

    expected = case["expected"][region]
    schema_errors = _validate_case_schema(case_id, case)
    image_errors = _check_image_paths(case_id, case)
    preflight_errors = schema_errors + image_errors

    if preflight_errors:
        return {
            "case_id": case_id,
            "region": region,
            "passed": False,
            "request_id": None,
            "preflight_errors": preflight_errors,
            "assertions": [],
            "detected_nummers": [],
        }

    if dry_run:
        return {
            "case_id": case_id,
            "region": region,
            "passed": True,
            "request_id": None,
            "dry_run": True,
            "assertions": [],
            "detected_nummers": [],
        }

    request_id = generate_request_id()
    camera_pairs = _build_camera_pairs(case)
    result = await run_pipeline(
        camera_pairs,
        request_id,
        bestekpost_filter=case.get("bestekpost_filter"),
        report_fields=case.get("report_fields"),
        region=region,
    )

    agent1_json = result.get("agent1_json", {})
    agent2_json = result.get("agent2_json", {})
    passed, assertions = _evaluate_assertions(agent1_json, agent2_json, expected)
    nummers = [
        str(bp.get("nummer", ""))
        for bp in agent2_json.get("bestekposten", [])
    ]

    return {
        "case_id": case_id,
        "region": region,
        "passed": passed,
        "request_id": request_id,
        "assertions": assertions,
        "detected_nummers": nummers,
    }


def _print_results_table(results: list[dict]) -> None:
    print()
    print(f"{'CASE':<32} {'REGION':<10} {'RESULT':<8} REQUEST_ID")
    print("-" * 72)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        rid = r.get("request_id") or "-"
        print(f"{r['case_id']:<32} {r['region']:<10} {status:<8} {rid}")
        for err in r.get("preflight_errors", []):
            print(f"  ! {err}")
        for a in r.get("assertions", []):
            if not a["passed"]:
                print(f"  x [{a['type']}] {a['message']}")


def _write_outputs(
    results: list[dict],
    region_label: str,
    output_dir: Path,
    dry_run: bool,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{ts}__{region_label}.json"
    md_path = output_dir / f"{ts}__{region_label}.md"

    passed_count = sum(1 for r in results if r["passed"])
    payload = {
        "timestamp": ts,
        "region": region_label,
        "dry_run": dry_run,
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "results": results,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        f"# Eval run {ts} ({region_label})",
        "",
        f"**Passed:** {passed_count} / {len(results)}",
        "",
    ]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"## {r['case_id']} ({r['region']}) — {status}")
        if r.get("request_id"):
            lines.append(f"- request_id: `{r['request_id']}` (see `logs/` JSONL)")
        for err in r.get("preflight_errors", []):
            lines.append(f"- preflight: {err}")
        for a in r.get("assertions", []):
            mark = "ok" if a["passed"] else "FAIL"
            lines.append(f"- [{mark}] {a['type']}: {a['value']} — {a['message']}")
        if r.get("detected_nummers"):
            lines.append(f"- detected: {', '.join(r['detected_nummers'])}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


async def _main_async(args: argparse.Namespace) -> int:
    case_filter = args.case if args.case else None
    cases = _discover_cases(case_filter)
    if not cases:
        print("No evaluation cases found.", file=sys.stderr)
        return 1

    if args.list_cases:
        return _list_cases(case_filter)

    limit = args.limit if args.limit is not None else args.max_cases
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR

    work_items: list[tuple[str, Path, str]] = []
    for case_id, case_path in cases:
        case = _load_case(case_path)
        for region in _regions_for_case(case, args.region):
            if region not in case.get("expected", {}):
                print(
                    f"Warning: case '{case_id}' has no expectations for region '{region}', skipping.",
                    file=sys.stderr,
                )
                continue
            work_items.append((case_id, case_path, region))

    if limit is not None:
        work_items = work_items[:limit]

    if not work_items:
        print("No (case, region) work items to run.", file=sys.stderr)
        return 1

    results: list[dict] = []
    for case_id, case_path, region in work_items:
        case = _load_case(case_path)
        print(f"Running {case_id} [{region}] …")
        result = await _run_case_region(case_id, case, region, args.dry_run)
        results.append(result)

    _print_results_table(results)
    region_label = args.region if args.region != "both" else "both"
    json_path, md_path = _write_outputs(results, region_label, output_dir, args.dry_run)
    print(f"\nResults written to:\n  {json_path}\n  {md_path}")

    if any(not r["passed"] for r in results):
        return 1
    return 0


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Run evaluation cases against the pipeline.")
    parser.add_argument(
        "--region",
        choices=("flemish", "walloon", "both"),
        default="both",
        help="Region(s) to evaluate (default: both)",
    )
    parser.add_argument(
        "--case",
        action="append",
        metavar="ID",
        help="Run only this case id (repeatable)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Max number of (case, region) runs",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        metavar="N",
        dest="max_cases",
        help="Alias for --limit",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List discovered cases and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate case files and image paths without calling the model",
    )
    parser.add_argument(
        "--output-dir",
        metavar="PATH",
        help="Override output directory (default: evals/results/)",
    )
    args = parser.parse_args()

    if args.list_cases:
        sys.exit(_list_cases(args.case if args.case else None))

    exit_code = asyncio.run(_main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
