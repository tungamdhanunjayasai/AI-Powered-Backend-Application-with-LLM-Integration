# Tri9T AI — CT-200 Document Intelligence & QA Traceability API

A focused FastAPI service that ingests the supplied CardioTrack CT-200 PDF manuals, reconstructs a versioned hierarchy, pins named selections to exact source text, generates structured QA test ideas, and exposes staleness when source requirements change.

## Features

- PDF text extraction using PyMuPDF, with explicit warnings for pages that have no extractable text (OCR is not silently faked).
- Section/subsection hierarchy, parent links, body text, page range, metadata, SHA-256 content hashes.
- Versioned ingestion; source files are immutable per version.
- Logical node matching by normalized numbered heading + title + duplicate occurrence.
- Browse top-level sections, fetch nodes/children, search heading/body.
- Version comparison with lightweight word-level diffs.
- Version-pinned named selections that store source text and hashes.
- LLM-generated 3–5 QA test ideas with Pydantic validation, requirement-reference validation, and deterministic fallback.
- Generated cases retain links to selection items and their exact source version/hash.
- Retrieval endpoint exposes staleness against the latest version.
- Repeat generation returns the previous generation by default; `force_new=true` creates another.

## Stack

Python, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, PyMuPDF, pytest. An optional OpenAI-compatible chat-completions endpoint can be configured; offline fallback makes the end-to-end flow demonstrable without an API key.

## Setup

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env  # Windows; optional
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> for interactive Swagger docs.

The provided `data/ct200_manual.pdf` and `data/ct200_manual_v2.pdf` are included as assignment fixtures.

## End-to-end v1 → v2 flow

In a second terminal, from the repository root:

```bash
# 1. Ingest version 1
curl -X POST "http://127.0.0.1:8000/documents/ingest-path?path=data/ct200_manual.pdf&version_number=1"

# 2. Ingest version 2 of the same logical document
curl -X POST "http://127.0.0.1:8000/documents/ingest-path?path=data/ct200_manual_v2.pdf&version_number=2"

# 3. List documents and versions
curl http://127.0.0.1:8000/documents
curl http://127.0.0.1:8000/documents/1/versions

# 4. Search for a requirement such as battery life / inflation / E6
curl "http://127.0.0.1:8000/nodes?q=battery"
```

Use `/docs` to select a node from version 1, create a selection with `POST /selections`, then `POST /generations`. Retrieve that generation again at `GET /generations/{generation_id}` after ingesting v2; the response includes `is_stale` and per-requirement `traceability`.

Example selection body:
```json
{"name":"Battery behavior in v1","node_ids":[1]}
```

Example generation body:
```json
{"selection_id":1}
```

To force a new generation for an existing selection:
```json
{"selection_id":1,"force_new":true}
```

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/documents/ingest` | Upload a PDF as multipart form data |
| POST | `/documents/ingest-path` | Ingest a local PDF path (for demo/testing) |
| GET | `/documents` | List documents |
| GET | `/documents/{id}/versions` | List versions |
| GET | `/documents/{id}/sections?version=1` | Top-level sections |
| GET | `/nodes/{id}` | Node, full text, immediate children |
| GET | `/nodes?q=pressure&version_id=1` | Search/filter |
| GET | `/nodes/{id}/changes` | Same logical node across versions |
| GET | `/documents/{id}/compare?from_version=1&to_version=2` | Added/removed/changed/unchanged nodes |
| POST | `/selections` | Create version-pinned selection |
| GET | `/selections/{id}` | Retrieve selection snapshots |
| POST | `/generations` | Generate test cases |
| GET | `/generations/{id}` | Retrieve cases plus current staleness |
| GET | `/generations?selection_id=1` | Retrieve generations by selection |
| GET | `/generations?node_id=1` | Retrieve generations by source node |

## Optional LLM configuration

Copy `.env.example` to `.env` and set the variables, then load the file in your shell or use a dotenv runner. `LLM_BASE_URL` is the OpenAI-compatible API root (the service appends `/chat/completions`), `LLM_API_KEY`, and `LLM_MODEL`. Without all three, the local deterministic generator is used. Malformed responses, schema errors, invalid reference keys, network failures, and wrong case counts are caught and fall back to deterministic output; the validation error is retained.

## Parser design and known limits

The update note explicitly says to parse the PDF directly rather than a Markdown file. The parser uses PyMuPDF's text spans and page metadata, detects numbered headings, reconstructs parents with a stack, and preserves paragraphs/lists in body text and metadata. Table extraction is best-effort: many PDF tables are visually arranged columns rather than tagged table structures, so table candidates are flagged for review. Pages with no text layer are reported as requiring OCR; OCR is not configured by default.

This is intentionally CT-200-specific, not a generic parser for arbitrary PDFs. It preserves duplicate heading occurrences as distinct nodes. Section labels and page layout irregularities can still defeat heuristics; review `/documents/{id}/compare`, extraction warnings, and fixture-based tests before relying on the result.

## Version matching and staleness

A logical key is derived from normalized heading identity plus occurrence count, so two same-title nodes in one version do not collapse. The content hash is based on normalized heading and that node's own body text (not its children), so a child change does not automatically mark the parent content as changed. When a selection is created, it stores the node/version IDs, logical key, heading/body snapshot, and hash. A generated case points to the immutable selection item. At retrieval, the API finds the corresponding logical key in the latest version and compares hashes.

Known limits: a section rename can appear as removal+addition; duplicate sections reordered between versions can match by occurrence rather than semantics; normalization can miss semantic changes expressed with equivalent wording; a clinically important number change is detected as a text change but not automatically assigned a semantic risk score. No automatic regeneration is performed.

## Idempotency and failure policy

- Same PDF SHA-256 for the same document: return existing version rather than duplicating it.
- Same selection submitted to generation again: return the most recent generation unless `force_new=true`.
- LLM output must parse as JSON, satisfy Pydantic constraints, contain 3–5 cases, and reference known logical keys. Otherwise store a deterministic fallback and the failure reason.
- A parse with no text is rejected; a page without extractable text yields a warning and requires OCR rather than being silently treated as empty content.

## Tests

```bash
pytest -q
```

Tests cover heading levels, duplicate-heading disambiguation, actual PDF extraction, invalid PDF handling, v1/v2 re-ingestion and comparison, and version-pinned selection snapshots.
