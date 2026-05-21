# Vorderingsstaten Agent

Automated progress-report generation for construction sites, powered by
Azure OpenAI's vision models. Given before-and-after photos of a worksite,
this application identifies which construction activities have been carried
out, maps each observation to its corresponding *bestekpostnummer* (the
entries of the Belgian construction specification, or *bestek*), and
returns a richly annotated Markdown report that a site manager can use as
the first draft of a formal *vorderingsstaat* (progress statement).

The service is designed around an MVP principle: when the model is
uncertain about a detected activity, the report flags the item as needing
a manual check or an additional photo, rather than risk producing a wrong
entry. The goal is to accelerate reporting without compromising accuracy.

## Table of contents

1. [What the app does](#what-the-app-does)
2. [How it works under the hood](#how-it-works-under-the-hood)
3. [Quick start](#quick-start)
4. [Configuration](#configuration)
5. [HTTP endpoints](#http-endpoints)
6. [Project structure](#project-structure)
7. [Pipeline flow in detail](#pipeline-flow-in-detail)
8. [Prompt design and agent responsibilities](#prompt-design-and-agent-responsibilities)
9. [Limits and resource guardrails](#limits-and-resource-guardrails)
10. [Logging](#logging)
11. [Evaluation harness](#evaluation-harness)
12. [Knowledge base setup](#knowledge-base-setup)
13. [Troubleshooting](#troubleshooting)

## What the app does

A site manager visits the same camera positions at two different points in
time, takes a *before* photo and an *after* photo for each position, and
uploads those pairs through a simple browser interface (or directly via
the HTTP API). The service then:

1. **Looks at all the images together** and identifies what work has
   been performed across the entire set. Because the same activity is
   often visible from several angles, the model is told which images
   belong to which camera so it can reason across angles and deduplicate
   observations.
2. **Matches every detected activity to a specification entry**
   (*bestekpost*) by doing a semantic search over the *master-inhoudstafel*
   (the top-level table of contents of the specification).
3. **Enriches every matched entry** with the full requirement text,
   relevant quotes, open points, and a concrete next step, using a second
   semantic search across the *detail* parts of the specification.
4. **Renders a Markdown progress report** that first summarises what was
   seen per camera, then lists every specification item with its
   observations, requirements, source references, risks, and recommended
   follow-up action.

The result is a structured, auditable draft report that the user can edit
or export. Both the raw JSON produced by each agent is also returned, so
downstream systems can consume the data programmatically.

## How it works under the hood

The application is a small FastAPI service that orchestrates two
LLM-based agents and a vector store hosted on Azure OpenAI:

- **Agent 1 (vision + mapping)** sees every uploaded photo at once,
  together with a short text legend telling it which photo index belongs
  to which camera and whether it is the *voor* (before) or *na* (after)
  shot. It then searches the master specification index to find the right
  *bestekpostnummers* and returns a single flat list of detected items.
- **Agent 2 (enrichment)** takes Agent 1's list as input and performs its
  own retrieval against the detailed specification parts to fill in
  titles, requirements, source references, and suggested follow-ups.

Both agent calls use `reasoning={"effort": "high"}` to explicitly instruct the `gpt-5.2` deployment to use high reasoning/thinking, improving the quality of visual delta detection and semantic matching.

Between the two agents, the orchestrator performs a deterministic server
side merge of duplicate entries and enforces the low-confidence rule, so
the downstream report cannot silently drop or overwrite a warning. The
final Markdown is assembled from the enriched structure by the reporting
layer.

## Quick start

> Requires **Python 3.10 or newer** (the code uses the `X | None` union
> syntax). The instructions below assume a Windows shell; Linux or macOS
> commands are shown as comments.

### 1. Clone and enter the project

```bash
git clone <your-remote>
cd "Voortgangsstaat use case/Voortgangsstaten agent"
```

### 2. Create a virtual environment and activate it

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows (cmd or PowerShell)
# source .venv/bin/activate   # Linux / macOS
```

### 3. Install the Python dependencies

```bash
pip install -r requirements.txt
```

Dependencies are intentionally minimal: FastAPI for the HTTP layer,
Pillow for image processing, the OpenAI SDK for Azure calls, python
-dotenv for configuration, and psutil for system guardrails.

### 4. Configure the Azure credentials

```bash
copy .env.example .env
# Then open .env in an editor and set AZURE_OPENAI_API_KEY
```

See [Configuration](#configuration) for the full list of variables.

### 5. Initialise the knowledge base (one-time)

```bash
python -m scripts.init_kb
```

This uploads the specification files to a new Azure OpenAI vector store
and writes the resulting `VECTOR_STORE_ID` back into your `.env`. If a
`VECTOR_STORE_ID` is already set the script reuses the existing store
instead of creating a new one. See
[Knowledge base setup](#knowledge-base-setup) for details on what files
must be in place before running this step.

### 6. Start the web server

```bash
python -m app.main
```

The API is now available at `http://localhost:8000`. Navigate there in
your browser to see the built-in uploader, or call the endpoints directly
as documented below.

## Configuration

All configuration is driven by environment variables, typically loaded
from a `.env` file at the project root via `python-dotenv`.

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `AZURE_OPENAI_API_KEY` | yes | – | API key for the Azure OpenAI resource that hosts the vision-capable deployment and the vector store. |
| `AZURE_OPENAI_ENDPOINT` | no | `https://aidalh.cognitiveservices.azure.com/` | Azure OpenAI resource endpoint (runtime and `init_kb`). |
| `AZURE_OPENAI_DEPLOYMENT` | no | `gpt-5.4` | Deployment name passed as the `model` parameter in API calls. |
| `AZURE_OPENAI_API_VERSION` | no | `2025-04-01-preview` | API version for the runtime pipeline (`app/openai_client.py`). |
| `AZURE_OPENAI_INIT_KB_API_VERSION` | no | `2025-04-01-preview` | API version for vector-store uploads (`scripts/init_kb.py`). Independent from the runtime key so upload and inference can be pinned separately; normally keep both identical. |
| `VECTOR_STORE_ID_FLEMISH` | yes* | – | Vector store for the Flemish bestek. Set by `python -m scripts.init_kb --region flemish`. |
| `VECTOR_STORE_ID_WALLOON` | yes* | – | Vector store for the Walloon CCTB. Set by `python -m scripts.init_kb --region walloon`. |
| `VECTOR_STORE_ID` | no | – | Legacy fallback: used as `VECTOR_STORE_ID_FLEMISH` if the Flemish key is empty. |
| `LOG_DIR` | no | `logs` | Directory into which the per-request JSONL trace files are written. |

\* At least the store for the region you use must be set.

## HTTP endpoints

### `POST /progress-report`

The main endpoint. It accepts one or more *before/after* camera pairs as
`multipart/form-data`, runs the full pipeline, and returns both the
rendered Markdown report and the underlying JSON.

#### Request fields

| Field | Type | Description |
| --- | --- | --- |
| `before_images` | repeated file | One *before* photo per camera, in camera order. Required, minimum 1. |
| `after_images` | repeated file | One *after* photo per camera, in the same order as `before_images`. Required, length must match. |
| `camera_labels` | string | A JSON-encoded array of camera labels, one per pair, in the same order (for example `["Living", "Keuken"]`). If missing or invalid, the server falls back to `["Camera 1", "Camera 2", …]`. |
| `region` | string | `flemish` (default) or `walloon`. Selects vector store, prompts, and report language. |

The pairs must be aligned by position: `before_images[i]` and
`after_images[i]` are treated as the *voor* and *na* photos of
`camera_labels[i]`. See [Limits](#limits-and-resource-guardrails) for
file-count and size caps.

#### Example with two cameras

```bash
curl -X POST http://localhost:8000/progress-report \
  -F "before_images=@foto_voor_1.jpg" \
  -F "after_images=@foto_na_1.jpg" \
  -F "before_images=@foto_voor_2.jpg" \
  -F "after_images=@foto_na_2.jpg" \
  -F "camera_labels=[\"Living\", \"Keuken\"]"
```

#### Response shape

```json
{
  "markdown_report": "# Vorderingsstaat – Automatisch concept\n…",
  "agent1_json": {
    "bestekposten": [
      {
        "nummer": "30.14",
        "image_indices": [2, 4],
        "camera_labels": ["Living", "Keuken"],
        "observaties": ["Binnenmuur gepleisterd", "Plinten aangebracht"],
        "zekerheid": "hoog",
        "toelichting": "Zichtbaar afgewerkte pleisterlaag in beide beelden."
      }
    ],
    "globale_opmerkingen": null
  },
  "agent2_json": {
    "bestekposten": [
      {
        "nummer": "30.14",
        "titel": "Binnenpleisterwerk",
        "image_indices": [2, 4],
        "camera_labels": ["Living", "Keuken"],
        "zekerheid": "hoog",
        "zichtbaar_uitgevoerd": ["…"],
        "bestekeisen": ["…"],
        "bron": { "deel": "3", "sectie": "…", "fragmenten": ["…"] },
        "open_punten": ["…"],
        "volgende_stap": "…"
      }
    ],
    "aandachtspunten_globaal": [],
    "extra_input_nodig": []
  }
}
```

The three fields are always present. The Markdown is what a user usually
sees; the two JSON blobs are primarily there for integration, debugging,
and regression testing.

#### Error responses

- `400 Bad Request` – mismatched `before`/`after` counts, zero or more
  than `MAX_PAIRS` pairs, empty files, a file larger than `MAX_IMAGE_SIZE`,
  or a total request body larger than `MAX_TOTAL_SIZE`. The `detail`
  field describes which constraint was violated.
- `503 Service Unavailable` – the host machine does not currently have
  enough RAM or is too CPU-saturated to safely run the pipeline. The
  snapshot is included in the error detail.
- `500 Internal Server Error` – an unexpected pipeline failure. The full
  stack trace is written to the server log; the client receives only
  `"Internal pipeline error – see server logs."`.

### `GET /health`

Lightweight liveness and resources endpoint. Returns JSON with a `status`
key and a `resources` snapshot (CPU percentage, RAM free, total RAM,
etc.). Useful for monitoring or for debugging why a request returned a
`503`.

### `GET /`

Serves the built-in static uploader (`static/index.html`). This is a
plain HTML page that lets a user create and remove camera blocks,
preview the uploaded images, and submit the form to `POST
/progress-report`.

## Project structure

```text
app/
  main.py              FastAPI entry point (mounts static files, routes, uvicorn runner).
  api.py               POST /progress-report endpoint and request validation.
  orchestrator.py      Pipeline: image optimization → Agent 1 → Agent 2 → markdown.
  openai_client.py     Singleton AsyncAzureOpenAI client and prompt / schema loaders.
  kb.py                Agent 1 and Agent 2 calls (vision, file_search, structured output).
  reporting.py         Markdown rendering for the hybrid camera/bestekpost layout.
  models.py            Pydantic models matching the JSON schemas.
  logging_utils.py     Structured JSONL request logging with trace IDs.
  utils/
    image_processing.py   EXIF-transpose, resize, JPEG compression, base64 encoding.
    system_monitor.py     CPU/RAM guardrails and safe-concurrency helpers.
prompts/
  agent1_system.txt    System prompt for Agent 1 (vision + bestekpost mapping).
  agent2_system.txt    System prompt for Agent 2 (enrichment + detailed reporting).
schemas/
  agent1.bestekpostmapping.json   Strict JSON schema for Agent 1 output.
  agent2.output.json              Strict JSON schema for Agent 2 output.
scripts/
  init_kb.py           One-time vector-store upload of master + detail files.
  run_evals.py         Evaluation harness (regression cases, structured assertions).
evals/
  cases/               Per-scenario case.json + image path references.
  results/             Eval run output (gitignored).
static/
  index.html           Browser uploader (camera blocks, previews, results tabs).
logs/                  JSONL request logs (auto-created, gitignored).
```

## Pipeline flow in detail

The full request-to-response path is implemented in
[`app/orchestrator.py`](app/orchestrator.py) and proceeds as follows:

1. **Resource guardrail.** Before any expensive work, the server reads
   the current CPU and RAM via `psutil`. If free RAM is below 10% or CPU
   usage is above 90%, the request is rejected with HTTP 503. This
   protects both the requester and other concurrent users on shared
   hardware.
2. **Image optimisation (parallel).** Every uploaded image is passed
   through Pillow: first `ImageOps.exif_transpose` to fix rotated phone
   photos, then a resize to at most 2048px on the longest side, then a
   JPEG re-encode at quality 85. The result is base64-encoded as a
   `data:` URL. All `2 × N` optimisations run in parallel threads via
   `asyncio.gather`, so adding more cameras does not linearly increase
   latency at this step.
3. **Agent 1 — vision and mapping.** All optimised images, plus a plain
   text legend (`Foto 1 = Camera 1 voor`, `Foto 2 = Camera 1 na`, …),
   are sent to the vision-capable Azure deployment together with a
   `file_search` tool filtered to `category=master`. Agent 1 responds
   with a strict-schema JSON object containing a `bestekposten` array.
   If validation fails, the call is retried once.
4. **Agent 2 — enrichment.** Agent 1's JSON is forwarded to a second
   model call. Agent 2 has access to a `file_search` tool filtered to
   `category=details`, and is instructed to preserve `nummer`,
   `image_indices`, `camera_labels`, and `zekerheid` while adding
   `titel`, `zichtbaar_uitgevoerd`, `bestekeisen`, `bron`, `open_punten`,
   and `volgende_stap`. Like Agent 1, validation failures trigger a
   single retry.
5. **Low-confidence enforcement.** The orchestrator scans Agent 1's
   output for any *bestekpost* marked `zekerheid: laag`. For each such
   entry, it guarantees that Agent 2's output contains the warning
   `"Manuele check / extra foto nodig"` in `open_punten`, and that the
   top-level `extra_input_nodig` list mentions the *bestekpostnummer*
   and the cameras concerned. This rule cannot be bypassed by the
   model, because it is enforced deterministically in code.
6. **Deduplication and sort.** The `bestekposten` list is defensively
   merged (unique camera labels, image indices, and open points are
   combined for any duplicate *nummer*) and sorted alphabetically, so
   the resulting report has a stable ordering regardless of how the
   model listed its findings.
7. **Markdown rendering.** The final `Agent2Output` plus the ordered
   image list are passed to `render_markdown`. The template builds a
   short "Input" section listing which photo index belongs to which
   camera, a "Overzicht per camera" section that lists the
   *bestekpostnummers* seen per camera, a detailed "Bestekposten"
   section with one block per entry, and optional "Aandachtspunten
   (globaal)" and "Aanbevolen extra input" sections.
8. **Log and return.** A JSONL trace is persisted and the orchestrator
   returns the Markdown, Agent 1 JSON, and Agent 2 JSON to the API
   layer, which serialises them to the HTTP response.

## Prompt design and agent responsibilities

The two prompts are designed so that the split between them is stable
and debuggable, rather than relying on a single monolithic model call.

**Agent 1** (`prompts/agent1_system.txt`) focuses on **what is visible**.
Its job is to turn images into a small, deduplicated list of
*bestekpostnummers*, together with the image indices and camera labels
that support each observation, and a confidence label (`hoog`, `middel`,
or `laag`). It must not invent numbers: if it is not reasonably sure,
it chooses a more general parent item that does exist in the master
index, or omits the observation entirely.

**Agent 2** (`prompts/agent2_system.txt`) focuses on **what the
specification says**. It receives Agent 1's output as JSON and is
instructed to preserve all identifying fields as-is. For every entry it
retrieves detail fragments from the right `Deel-X` document, then
produces a structured enrichment: a clear title, bullet lists of what is
visibly done and of the relevant *bestekeisen*, a `bron` block with
quotes from the specification, a list of `open_punten`, and a single
concrete `volgende_stap`.

The reason for splitting the pipeline is that the two jobs have
fundamentally different failure modes: Agent 1 is a vision task, Agent 2
is a retrieval-augmented text task. By separating them we can inspect and
retry each one independently, and we can enforce deterministic rules
between them (see step 5 of the pipeline).

## Limits and resource guardrails

| Constant | Default | Where it is enforced | Purpose |
| --- | --- | --- | --- |
| `MAX_PAIRS` | 6 | [`app/api.py`](app/api.py) | Caps the number of camera blocks per request, protecting the vision model from very long image lists. |
| `MAX_IMAGE_SIZE` | 20 MB | [`app/api.py`](app/api.py) | Rejects individual uploads that are too large before the pipeline starts. |
| `MAX_TOTAL_SIZE` | 120 MB | [`app/api.py`](app/api.py) | Rejects the request as a whole if the combined size of all images exceeds this threshold. |
| `MAX_DIMENSION` | 2048 px | [`app/utils/image_processing.py`](app/utils/image_processing.py) | Resizes each image so the longest side is at most 2048 px before encoding. |
| `JPEG_QUALITY` | 85 | [`app/utils/image_processing.py`](app/utils/image_processing.py) | JPEG compression quality used when re-encoding. |
| `check_resources` | 10% free RAM / 90% CPU | [`app/utils/system_monitor.py`](app/utils/system_monitor.py) | Returns HTTP 503 when the host is under pressure. |

Change these by editing the constants in the referenced files. All
values are intentionally conservative for MVP deployment on modest
hardware.

## Logging

Every request writes a JSONL trace to `logs/<YYYY-MM-DD>.jsonl`
(controlled by `LOG_DIR`). Entries are keyed by a short hexadecimal
`request_id` and include:

- `image_optimization` with per-camera, per-role byte sizes,
- `agent1_raw_output` with the raw JSON returned by Agent 1,
- `agent1_retry` (only when a retry occurred) with the validation error,
- `agent2_raw_output` with the raw JSON returned by Agent 2,
- `agent2_retry` (only when a retry occurred) with the validation error,
- `agent1_usage` / `agent1_retry_usage` and `agent2_usage` / `agent2_retry_usage` with per-call latency and token counts (`input_tokens`, `output_tokens`, `total_tokens`, `reasoning_tokens`, plus a best-effort `raw_usage` dump),
- a final `summary` entry with elapsed time per step, aggregated `tokens` totals, and the overall request duration.

The trace files are plain JSON Lines: one JSON object per line, safe to
`cat`, `tail -f`, or ingest into any log aggregator that understands
JSONL.

## Evaluation harness

A small regression suite lives under `evals/cases/`. Each case is a
`case.json` that references before/after images (by default under
`Data AI toren/`) and defines **region-specific** expected outcomes:
required bestekpost/CCTB prefixes, forbidden prefixes, and keyword
substrings in observations. The same images are used for both Flemish
and Walloon runs; only the expectations differ.

**Prerequisite:** the image paths referenced in the case files must
exist on disk. On a fresh checkout without `Data AI toren/`, pre-flight
checks fail with an explicit message rather than an opaque error.

```bash
# List cases without calling the model
python -m scripts.run_evals --list-cases

# Validate case files and image paths only
python -m scripts.run_evals --region both --dry-run

# Full run (calls Azure — costs tokens)
python -m scripts.run_evals --region both

# Quick smoke: one (case, region) invocation
python -m scripts.run_evals --region flemish --case tower_cam1_jan_feb --limit 1
```

Results are written to `evals/results/<timestamp>__<region>.json` and
`.md`. Each case records its `request_id` so failures can be traced in
`logs/<date>.jsonl`. Exit code is `1` if any case fails.

## Region support (Flemish vs Walloon)

The built-in uploader and `POST /progress-report` accept a `region` form
field (`flemish` or `walloon`, default `flemish`):

| Region | Specification | Master index | Detail documents |
| --- | --- | --- | --- |
| `flemish` | Bouwtechnisch bestek (Vlaams) | `Master-inhoudstafel.txt` | `Deel-0` … `Deel-9` .docx |
| `walloon` | CCTB 01.13 (Wallon) | `Master-CCTB.txt` | `CCTB_01.13_docx/*.docx` |

Each region uses its **own Azure vector store** (`VECTOR_STORE_ID_FLEMISH`
and `VECTOR_STORE_ID_WALLOON`). Agent prompts and the rendered Markdown
report are in Dutch for Flemish and in French for Walloon.

### Walloon setup (one-time)

```bash
# 1. Generate the master index from the CCTB Word files
python -m scripts.build_walloon_master

# 2. Upload master + detail files to a new vector store
python -m scripts.init_kb --region walloon
```

Flemish setup is unchanged:

```bash
python -m scripts.init_kb --region flemish
```

If your `.env` still has the legacy `VECTOR_STORE_ID` only, it is treated
as `VECTOR_STORE_ID_FLEMISH` until you migrate.

## Knowledge base setup

Before you can run the service, the Azure OpenAI vector store for your
chosen region must contain the specification files. The bundled
[`scripts/init_kb.py`](scripts/init_kb.py) uploads (per `--region`):

- `Master-inhoudstafel.txt` — a plain-text list of all
  *bestekpostnummers*, used by Agent 1 for its initial mapping search.
  Tagged with metadata `category=master`.
- `BouwtechnischBestekWoningbouw_20151222_ytdo1q/Deel-<0..9>*.docx` —
  the detailed specification parts. Each is tagged with
  `category=details` and a `deel` metadata key equal to its leading
  digit, so Agent 2 can filter its retrieval down to the relevant part.

Running `python -m scripts.init_kb` will either create a new vector
store or reuse the existing `VECTOR_STORE_ID`. The script waits for each
uploaded file to reach status `completed` before moving on, and writes
the resulting vector-store ID back into `.env` on success.

## Troubleshooting

- **"VECTOR_STORE_ID_FLEMISH is not set" (or Walloon equivalent).** Run
  `python -m scripts.init_kb --region flemish` or `--region walloon`.
  For Walloon, run `python -m scripts.build_walloon_master` first.
- **HTTP 503 on every request.** Check `/health`. If `ram_percent_free`
  is below 10 or `cpu_percent` is above 90, close other programs or
  relax the thresholds in `app/utils/system_monitor.py`.
- **"Image exceeds max size".** Either shrink the image before uploading
  or raise `MAX_IMAGE_SIZE` in `app/api.py`.
- **Report numbers look wrong.** Inspect the `agent1_raw_output` entry
  in today's JSONL log. If Agent 1 is producing confident but incorrect
  numbers, the likely cause is a missing or outdated
  `Master-inhoudstafel.txt` in the vector store; re-run `init_kb` after
  updating it.
- **Rotated phone photos.** The service already applies EXIF transpose
  during optimisation, so rotated input should render upright. If it
  does not, the source image may have no EXIF orientation tag and needs
  to be rotated manually before upload.
