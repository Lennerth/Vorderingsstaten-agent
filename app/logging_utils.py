"""Structured JSONL request logging with trace IDs."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))


def generate_request_id() -> str:
    return uuid.uuid4().hex[:12]


def format_duration_mmss(seconds: float) -> str:
    """Format seconds as mm:ss (e.g. 65.3 -> '1:05')."""
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def format_timings_display(timings: dict[str, float]) -> dict[str, str]:
    """Build human-readable mm:ss map from numeric timing seconds."""
    return {label: format_duration_mmss(duration) for label, duration in timings.items()}


class RequestLogger:
    """Accumulates structured log entries per request and flushes to JSONL."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.start_time = time.time()
        self.entries: list[dict] = []
        self.timings: dict[str, float] = {}
        self.token_totals: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "reasoning_tokens": 0,
        }

    def log_step(self, step: str, data: dict | None = None):
        elapsed_s = time.time() - self.start_time
        entry = {
            "request_id": self.request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": int(elapsed_s * 1000),
            "elapsed_s": round(elapsed_s, 3),
            "elapsed_display": format_duration_mmss(elapsed_s),
            "step": step,
            **(data or {}),
        }
        self.entries.append(entry)
        logger.info(
            "[%s] %s – %s",
            self.request_id,
            step,
            entry["elapsed_display"],
        )

    def add_timing(self, label: str, duration_s: float):
        self.timings[label] = round(duration_s, 3)

    def add_tokens(self, meta: dict) -> None:
        for key in self.token_totals:
            value = meta.get(key)
            if isinstance(value, int):
                self.token_totals[key] += value

    def persist(self):
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{date_str}.jsonl"

        summary = {
            "request_id": self.request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "summary",
            "timings": self.timings,
            "timings_display": format_timings_display(self.timings),
            "tokens": self.token_totals,
        }

        with open(log_file, "a", encoding="utf-8") as fh:
            for entry in self.entries:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            fh.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")

        logger.info(
            "[%s] Logs persisted to %s (%d entries)",
            self.request_id,
            log_file,
            len(self.entries) + 1,
        )
