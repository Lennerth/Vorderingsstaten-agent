"""
Initialise the OpenAI vector store for Vorderingsstaten Agent.

Creates or reuses a vector store per region and uploads:
  Flemish (--region flemish):
    - Master-inhoudstafel.txt  →  {"category": "master"}
    - Deel-0 … Deel-9 .docx    →  {"category": "details", "deel": "N"}

  Walloon (--region walloon):
    - Master-CCTB.txt          →  {"category": "master"}
    - CCTB_01.13_docx/*.docx   →  {"category": "details", "deel": "T0"|"A"|"Z"|…}

Saves VECTOR_STORE_ID_FLEMISH or VECTOR_STORE_ID_WALLOON to .env.

Usage:
    python -m scripts.init_kb --region flemish
    python -m scripts.init_kb --region walloon
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, set_key
from openai import AzureOpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BESTEK_DIR = PROJECT_ROOT / "BouwtechnischBestekWoningbouw_20151222_ytdo1q"
CCTB_DIR = PROJECT_ROOT / "CCTB_01.13_docx"
ENV_PATH = PROJECT_ROOT / ".env"
AZURE_ENDPOINT = "https://aidalh.cognitiveservices.azure.com/"
AZURE_API_VERSION = "2025-03-01-preview"

REGION_ENV_KEYS = {
    "flemish": "VECTOR_STORE_ID_FLEMISH",
    "walloon": "VECTOR_STORE_ID_WALLOON",
}

REGION_STORE_NAMES = {
    "flemish": "Vorderingsstaten Bestek (Vlaams)",
    "walloon": "Vorderingsstaten CCTB (Wallon)",
}


def _wait_for_file(client: AzureOpenAI, vs_id: str, file_id: str, timeout: int = 300):
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


def _upload_file(
    client: AzureOpenAI,
    vs_id: str,
    path: Path,
    attributes: dict,
    uploaded: list[str],
) -> None:
    print(f"\nUploading {path.name} …")
    with open(path, "rb") as fh:
        file_obj = client.files.create(file=fh, purpose="assistants")
    client.vector_stores.files.create(
        vector_store_id=vs_id,
        file_id=file_obj.id,
        attributes=attributes,
    )
    print(f"  ✓ file_id={file_obj.id}  (waiting for indexing …)")
    _wait_for_file(client, vs_id, file_obj.id)
    print("  ✓ indexed")
    uploaded.append(path.name)


def _deel_from_cctb_filename(path: Path) -> str:
    name = path.stem.upper()
    if name.startswith("A "):
        return "A"
    if name.startswith("Z "):
        return "Z"
    match = re.search(r"\bT(\d+)\b", name)
    if match:
        return f"T{match.group(1)}"
    return "Z"


def init_flemish(client: AzureOpenAI, vs_id: str, uploaded: list[str]) -> None:
    master_path = PROJECT_ROOT / "Master-inhoudstafel.txt"
    if not master_path.is_file():
        raise FileNotFoundError(f"Missing {master_path}")

    _upload_file(
        client,
        vs_id,
        master_path,
        {"category": "master"},
        uploaded,
    )

    if not BESTEK_DIR.is_dir():
        raise FileNotFoundError(f"Missing Flemish bestek directory: {BESTEK_DIR}")

    for docx_path in sorted(BESTEK_DIR.glob("Deel-*.docx")):
        match = re.match(r"Deel-(\d)", docx_path.name)
        if not match:
            continue
        deel = match.group(1)
        _upload_file(
            client,
            vs_id,
            docx_path,
            {"category": "details", "deel": deel},
            uploaded,
        )


def init_walloon(client: AzureOpenAI, vs_id: str, uploaded: list[str]) -> None:
    master_path = PROJECT_ROOT / "Master-CCTB.txt"
    if not master_path.is_file():
        raise FileNotFoundError(
            f"Missing {master_path}. Run `python -m scripts.build_walloon_master` first."
        )

    _upload_file(
        client,
        vs_id,
        master_path,
        {"category": "master"},
        uploaded,
    )

    if not CCTB_DIR.is_dir():
        raise FileNotFoundError(f"Missing Walloon CCTB directory: {CCTB_DIR}")

    for docx_path in sorted(CCTB_DIR.glob("*.docx")):
        deel = _deel_from_cctb_filename(docx_path)
        _upload_file(
            client,
            vs_id,
            docx_path,
            {"category": "details", "deel": deel},
            uploaded,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload specification files to Azure vector store.")
    parser.add_argument(
        "--region",
        choices=("flemish", "walloon"),
        default="flemish",
        help="Which specification corpus to upload (default: flemish)",
    )
    args = parser.parse_args()
    region = args.region
    env_key = REGION_ENV_KEYS[region]

    load_dotenv(ENV_PATH)
    client = AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=AZURE_API_VERSION,
    )

    vs_id = os.getenv(env_key, "").strip()
    if not vs_id and region == "flemish":
        vs_id = os.getenv("VECTOR_STORE_ID", "").strip()

    if vs_id:
        print(f"Reusing existing vector store for {region}: {vs_id}")
    else:
        vs = client.vector_stores.create(name=REGION_STORE_NAMES[region])
        vs_id = vs.id
        print(f"Created vector store for {region}: {vs_id}")

    uploaded: list[str] = []

    if region == "flemish":
        init_flemish(client, vs_id, uploaded)
    else:
        init_walloon(client, vs_id, uploaded)

    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    success = set_key(str(ENV_PATH), env_key, vs_id)
    if not success:
        raise RuntimeError(f"Failed to write {env_key} to {ENV_PATH}")

    saved_values = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        saved_values[key.strip()] = value.strip().strip("'\"")

    if saved_values.get(env_key) != vs_id:
        raise RuntimeError(
            f"{env_key} was not persisted to {ENV_PATH}; expected {vs_id}."
        )

    print(f"\n{'=' * 60}")
    print(f"Done!  {env_key}={vs_id}")
    print(f"Uploaded {len(uploaded)} files: {', '.join(uploaded)}")
    print(f".env updated at {ENV_PATH}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
