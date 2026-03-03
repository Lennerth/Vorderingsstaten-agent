"""Singleton AsyncAzureOpenAI client and helpers to load prompts / schemas."""

from __future__ import annotations

import json
import os
from pathlib import Path

from openai import AsyncAzureOpenAI

_client: AsyncAzureOpenAI | None = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AZURE_ENDPOINT = "https://aidalh.cognitiveservices.azure.com/"
AZURE_DEPLOYMENT = "gpt-5.2"
AZURE_API_VERSION = "2025-03-01-preview"


def get_client() -> AsyncAzureOpenAI:
    global _client
    if _client is None:
        _client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=AZURE_API_VERSION,
        )
    return _client


def get_model() -> str:
    # For Azure OpenAI, model must be the deployment name.
    return AZURE_DEPLOYMENT


def get_vector_store_id() -> str:
    vs_id = os.getenv("VECTOR_STORE_ID", "").strip()
    if not vs_id:
        raise RuntimeError(
            "VECTOR_STORE_ID is not set. Run `python -m scripts.init_kb` first."
        )
    return vs_id


def load_prompt(name: str) -> str:
    return (PROJECT_ROOT / "prompts" / name).read_text(encoding="utf-8")


def load_schema(name: str) -> dict:
    return json.loads(
        (PROJECT_ROOT / "schemas" / name).read_text(encoding="utf-8")
    )
