# Vorderingsstaten Agent – MVP

Automated progress-report generation from construction-site before/after photos.
Uses OpenAI vision (GPT-4o) + vector-store file search to map visible work to
*bestekpostnummers* and generate a detailed Markdown report.

## Quick start

```bash
# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
copy .env.example .env
# Edit .env → set OPENAI_API_KEY

# 4. Initialise the knowledge base (uploads files to OpenAI vector store)
python -m scripts.init_kb

# 5. Start the API
python -m app.main
# → http://localhost:8000
```

## Endpoints

### `POST /progress-report`

Upload two images (multipart/form-data):

| Field    | Type | Description            |
| -------- | ---- | ---------------------- |
| `before` | file | Photo **before** works |
| `after`  | file | Photo **after** works  |

**Example (curl):**

```bash
curl -X POST http://localhost:8000/progress-report \
  -F "before=@foto_voor.jpg" \
  -F "after=@foto_na.jpg"
```

**Response (JSON):**

```json
{
  "markdown_report": "# Vorderingsstaat – Automatisch concept\n…",
  "agent2_json": { "transitions": [ … ] },
  "agent1_json": { "transitions": [ … ] },
  "retrieval_log": [ { "bestekpostnummer": "30.14", … } ]
}
```

### `GET /health`

Returns server status and current CPU / RAM metrics.

## Project structure

```
app/
  main.py              FastAPI entry point
  api.py               POST /progress-report endpoint
  orchestrator.py      Agent 1 → parallel retrieval → Agent 2 pipeline
  openai_client.py     AsyncOpenAI singleton + helpers
  kb.py                File-search & vector-store calls
  reporting.py         Markdown rendering from Agent 2 output
  models.py            Pydantic request / response models
  logging_utils.py     Structured JSONL logging with trace IDs
  utils/
    image_processing.py   Resize / compress with Pillow
    system_monitor.py     CPU / RAM guardrails
prompts/
  agent1_system.txt    System prompt for Agent 1 (vision + mapping)
  agent2_system.txt    System prompt for Agent 2 (enrichment)
schemas/
  agent1.bestekpostmapping.json   OpenAI strict JSON schema for Agent 1
  agent2.output.json              OpenAI strict JSON schema for Agent 2
scripts/
  init_kb.py           One-time vector-store initialisation
logs/                  JSONL request logs (auto-created)
```

## Pipeline flow

1. **Resource check** – reject with 503 if RAM < 10 % free or CPU > 90 %.
2. **Image optimisation** – resize to max 2048 px, JPEG compress.
3. **Agent 1** – GPT-4o vision + `file_search` (category=master) → structured
   JSON with bestekpostnummers and confidence.
4. **Parallel detail retrieval** – `asyncio.gather` with semaphore (N-1 CPUs),
   direct vector-store search filtered by `category=details` and `deel`.
5. **Agent 2** – receives Agent 1 JSON + detail fragments → enriched report.
6. **MVP rule** – if confidence is *laag*, force
   "Manuele check / extra foto nodig" in output.
7. **Render** – Markdown report from the template.
8. **Log** – full JSONL trace in `logs/<date>.jsonl`.

## Logging

Every request writes detailed JSONL entries to `logs/`:
- `request_id`, timestamp, elapsed milliseconds per step.
- Agent 1 raw output and parsed JSON.
- Per bestekpostnummer: query, fragments retrieved.
- Agent 2 input context and output.
- Timing summary (image optimisation, agent1, detail retrieval, agent2, total).

## Environment variables

| Variable           | Required | Default   | Description                     |
| ------------------ | -------- | --------- | ------------------------------- |
| `OPENAI_API_KEY`   | yes      | –         | OpenAI API key                  |
| `VECTOR_STORE_ID`  | yes      | –         | Set by `init_kb.py`             |
| `OPENAI_MODEL`     | no       | `gpt-4o`  | Model for Agent 1 & 2          |
| `LOG_DIR`          | no       | `logs`    | Directory for JSONL request logs|
