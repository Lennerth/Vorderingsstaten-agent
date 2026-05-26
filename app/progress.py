"""In-memory progress tracking for async report jobs."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from app.logging_utils import format_duration_mmss

DEFAULT_TTL_S = 3600
DEFAULT_MAX_CONCURRENT = 1

STEP_IDS = (
    "upload_validation",
    "video_extraction",
    "image_optimization",
    "agent1",
    "agent2",
    "report_generation",
)


@dataclass
class StepState:
    id: str
    status: str = "pending"
    duration_s: float | None = None
    duration_display: str | None = None
    elapsed_display: str | None = None
    started_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "status": self.status}
        if self.duration_display is not None:
            payload["duration_display"] = self.duration_display
        if self.elapsed_display is not None:
            payload["elapsed_display"] = self.elapsed_display
        return payload


@dataclass
class JobProgress:
    request_id: str
    status: str = "pending"
    steps: list[StepState] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
            "result": self.result,
            "error": self.error,
        }


class ProgressStore:
    """Thread-safe in-memory job progress store with TTL cleanup."""

    def __init__(
        self,
        *,
        ttl_s: int | None = None,
        max_concurrent: int | None = None,
    ):
        self._jobs: dict[str, JobProgress] = {}
        self._lock = threading.Lock()
        self._ttl_s = ttl_s if ttl_s is not None else _parse_int_env(
            "PROGRESS_JOB_TTL_S", DEFAULT_TTL_S, min_val=60
        )
        self._max_concurrent = max_concurrent if max_concurrent is not None else _parse_int_env(
            "PROGRESS_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT, min_val=1
        )

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            request_id
            for request_id, job in self._jobs.items()
            if now - job.updated_at > self._ttl_s
        ]
        for request_id in expired:
            del self._jobs[request_id]

    def can_start_job(self) -> bool:
        with self._lock:
            self._cleanup_expired()
            running = sum(
                1 for job in self._jobs.values() if job.status in {"pending", "running"}
            )
            return running < self._max_concurrent

    def create_job(self, request_id: str, step_ids: tuple[str, ...] = STEP_IDS) -> JobProgress:
        with self._lock:
            self._cleanup_expired()
            running = sum(
                1 for job in self._jobs.values() if job.status in {"pending", "running"}
            )
            if running >= self._max_concurrent:
                raise RuntimeError("Another report job is already running.")
            job = JobProgress(
                request_id=request_id,
                status="pending",
                steps=[StepState(id=step_id) for step_id in step_ids],
            )
            self._jobs[request_id] = job
            return job

    def get_job(self, request_id: str) -> JobProgress | None:
        with self._lock:
            self._cleanup_expired()
            return self._jobs.get(request_id)

    def set_status(self, request_id: str, status: str) -> None:
        with self._lock:
            job = self._jobs.get(request_id)
            if not job:
                return
            job.status = status
            job.updated_at = time.time()

    def update_step(self, request_id: str, step_id: str, status: str, **extra) -> None:
        with self._lock:
            job = self._jobs.get(request_id)
            if not job:
                return
            step = next((item for item in job.steps if item.id == step_id), None)
            if step is None:
                return
            now = time.time()
            if status == "running":
                step.status = "running"
                step.started_at = now
                step.elapsed_display = "0:00"
            elif status == "done":
                duration_s = extra.get("duration_s")
                if duration_s is None and step.started_at is not None:
                    duration_s = now - step.started_at
                step.status = "done"
                if duration_s is not None:
                    step.duration_s = round(float(duration_s), 3)
                    step.duration_display = format_duration_mmss(duration_s)
                step.elapsed_display = None
            elif status == "error":
                step.status = "error"
            job.status = "running"
            job.updated_at = now

    def complete_job(self, request_id: str, result: dict) -> None:
        with self._lock:
            job = self._jobs.get(request_id)
            if not job:
                return
            job.status = "complete"
            job.result = result
            job.updated_at = time.time()

    def fail_job(self, request_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(request_id)
            if not job:
                return
            job.status = "error"
            job.error = error
            job.updated_at = time.time()


def _parse_int_env(name: str, default: int, *, min_val: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if min_val is not None and value < min_val:
        return default
    return value


progress_store = ProgressStore()
