"""Singleton AsyncAzureOpenAI client and helpers to load prompts / schemas."""

from __future__ import annotations

import json
import os
from pathlib import Path

from openai import AsyncAzureOpenAI

from app.config import (
    DEFAULT_AZURE_API_VERSION,
    DEFAULT_AZURE_DEPLOYMENT,
    DEFAULT_AZURE_ENDPOINT,
)
from app.regions import PROMPT_FILES, VECTOR_STORE_ENV_KEYS, normalize_region

_client: AsyncAzureOpenAI | None = None
_deployment: str | None = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _azure_endpoint() -> str:
    return os.getenv("AZURE_OPENAI_ENDPOINT", DEFAULT_AZURE_ENDPOINT).strip()


def _azure_deployment() -> str:
    return os.getenv("AZURE_OPENAI_DEPLOYMENT", DEFAULT_AZURE_DEPLOYMENT).strip()


def _azure_api_version() -> str:
    return os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_API_VERSION).strip()


def get_client() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=_azure_endpoint(),
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=_azure_api_version(),
        )
    return _client


def get_model() -> str:
    global _deployment
    if _deployment is None:
        _deployment = _azure_deployment()
    return _deployment


def get_vector_store_id(region: str = "flemish") -> str:
    region = normalize_region(region)
    env_key = VECTOR_STORE_ENV_KEYS[region]
    vs_id = os.getenv(env_key, "").strip()

    if not vs_id and region == "flemish":
        vs_id = os.getenv("VECTOR_STORE_ID", "").strip()

    if not vs_id:
        raise RuntimeError(
            f"{env_key} is not set. Run `python -m scripts.init_kb --region {region}` first."
        )
    return vs_id


def prompt_filename(agent: str, region: str = "flemish") -> str:
    region = normalize_region(region)
    if agent not in ("agent1", "agent2"):
        raise ValueError(f"Unknown agent '{agent}'")
    return PROMPT_FILES[region][agent]


def load_prompt(name: str) -> str:
    return (PROJECT_ROOT / "prompts" / name).read_text(encoding="utf-8")


def load_region_prompt(agent: str, region: str = "flemish") -> str:
    return load_prompt(prompt_filename(agent, region))


def load_schema(name: str) -> dict:
    return json.loads(
        (PROJECT_ROOT / "schemas" / name).read_text(encoding="utf-8")
    )
