"""
Initialise the OpenAI vector store for Vorderingsstaten Agent.

Creates one vector store, uploads:
  - Master-inhoudstafel.txt  →  metadata  {"category": "master"}
  - Deel-0 … Deel-9 .docx   →  metadata  {"category": "details", "deel": "N"}

Saves VECTOR_STORE_ID to .env (idempotent – reuses an existing ID).

Usage:
    python -m scripts.init_kb
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, set_key
from openai import AzureOpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BESTEK_DIR = PROJECT_ROOT / "BouwtechnischBestekWoningbouw_20151222_ytdo1q"
ENV_PATH = PROJECT_ROOT / ".env"
AZURE_ENDPOINT = "https://aidalh.cognitiveservices.azure.com/"
AZURE_API_VERSION = "2025-03-01-preview"


def _wait_for_file(client: AzureOpenAI, vs_id: str, file_id: str, timeout: int = 120):
    """Poll until a vector-store file reaches status 'completed'."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        status = client.vector_stores.files.retrieve(
            vector_store_id=vs_id, file_id=file_id
        ).status
        if status == "completed":
            return
        if status == "failed":
            raise RuntimeError(f"File {file_id} processing failed")
        time.sleep(2)
    raise TimeoutError(f"File {file_id} did not complete within {timeout}s")


def main() -> None:
    load_dotenv(ENV_PATH)
    client = AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=AZURE_API_VERSION,
    )

    # ── Reuse or create vector store ─────────────────────────────────────
    vs_id = os.getenv("VECTOR_STORE_ID", "").strip()
    if vs_id:
        print(f"Reusing existing vector store: {vs_id}")
    else:
        vs = client.vector_stores.create(name="Vorderingsstaten Bestek")
        vs_id = vs.id
        print(f"Created vector store: {vs_id}")

    uploaded: list[str] = []

    # ── Upload master ────────────────────────────────────────────────────
    master_path = PROJECT_ROOT / "Master-inhoudstafel.txt"
    print(f"\nUploading {master_path.name} …")
    with open(master_path, "rb") as fh:
        master_file = client.files.create(file=fh, purpose="assistants")
    client.vector_stores.files.create(
        vector_store_id=vs_id,
        file_id=master_file.id,
        attributes={"category": "master"},
    )
    print(f"  ✓ file_id={master_file.id}  (waiting for indexing …)")
    _wait_for_file(client, vs_id, master_file.id)
    print("  ✓ indexed")
    uploaded.append(master_path.name)

    # ── Upload detail parts ──────────────────────────────────────────────
    for docx_path in sorted(BESTEK_DIR.glob("Deel-*.docx")):
        match = re.match(r"Deel-(\d)", docx_path.name)
        if not match:
            continue
        deel = match.group(1)
        print(f"\nUploading {docx_path.name}  (deel={deel}) …")
        with open(docx_path, "rb") as fh:
            file_obj = client.files.create(file=fh, purpose="assistants")
        client.vector_stores.files.create(
            vector_store_id=vs_id,
            file_id=file_obj.id,
            attributes={"category": "details", "deel": deel},
        )
        print(f"  ✓ file_id={file_obj.id}  (waiting for indexing …)")
        _wait_for_file(client, vs_id, file_obj.id)
        print("  ✓ indexed")
        uploaded.append(docx_path.name)

    # ── Persist to .env ──────────────────────────────────────────────────
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    set_key(str(ENV_PATH), "VECTOR_STORE_ID", vs_id)

    print(f"\n{'='*60}")
    print(f"Done!  VECTOR_STORE_ID={vs_id}")
    print(f"Uploaded {len(uploaded)} files: {', '.join(uploaded)}")
    print(f".env updated at {ENV_PATH}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
