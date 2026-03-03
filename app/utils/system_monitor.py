"""CPU / RAM guardrails – uses at most N-1 cores and 90 % of free RAM."""

from __future__ import annotations

import os

import psutil


def get_system_resources() -> dict:
    cpu_count = os.cpu_count() or 1
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    return {
        "cpu_count": cpu_count,
        "cpu_percent": round(cpu_percent, 1),
        "ram_total_mb": round(mem.total / (1024 * 1024)),
        "ram_available_mb": round(mem.available / (1024 * 1024)),
        "ram_percent_used": round(mem.percent, 1),
        "ram_percent_free": round(100 - mem.percent, 1),
    }


def check_resources(
    min_free_ram_pct: float = 10.0,
    max_cpu_pct: float = 90.0,
) -> tuple[bool, dict]:
    """Return (ok, resource_snapshot).  ok=False means the server should 503."""
    resources = get_system_resources()
    ok = (
        resources["ram_percent_free"] >= min_free_ram_pct
        and resources["cpu_percent"] <= max_cpu_pct
    )
    return ok, resources


def get_safe_concurrency() -> int:
    """Max parallel async tasks – N-1 CPUs, halved when RAM is tight."""
    cpu_count = os.cpu_count() or 1
    safe = max(1, cpu_count - 1)
    mem = psutil.virtual_memory()
    if mem.percent > 80:
        safe = max(1, safe // 2)
    return safe
