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


class RequestLogger:
    """Accumulates structured log entries per request and flushes to JSONL."""

    def __init__(self, request_id: str):
        self.request_id = request_id
        self.start_time = time.time()
        self.entries: list[dict] = []
        self.timings: dict[str, float] = {}

    def log_step(self, step: str, data: dict | None = None):
        entry = {
            "request_id": self.request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": int((time.time() - self.start_time) * 1000),
            "step": step,
            **(data or {}),
        }
        self.entries.append(entry)
        logger.info("[%s] %s – %d ms", self.request_id, step, entry["elapsed_ms"])

    def add_timing(self, label: str, duration_s: float):
        self.timings[label] = round(duration_s, 3)

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
