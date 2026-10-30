# Local LLM Data Assistant API

Base URL when running locally: `http://127.0.0.1:8000`

The API processes one heavy job at a time. Pipeline submission endpoints return
`202 Accepted` immediately. Use the returned `status_url` to poll the job, then
download files from the returned artifact URLs.

## Authentication

If `LOCAL_AI_API_KEY` is configured, send it on every API request:

```http
X-API-Key: your-api-key
```

Without an API key, requests are accepted only from localhost. Remote access
without `LOCAL_AI_API_KEY` returns `403 Forbidden`.

## Common job response

Pipeline submission, job-list, and job-status endpoints use this shape:

```json
{
  "id": "71125a92-b96e-42e7-afe8-5d43d6981c42",
  "pipeline": "research",
  "status": "pending",
  "created_at": "2026-10-03T10:00:00Z",
  "started_at": null,
  "finished_at": null,
  "error": null,
  "artifacts": [
    {
      "name": "research_report.md",
      "url": "/jobs/71125a92-b96e-42e7-afe8-5d43d6981c42/artifacts/research_report.md"
    }
  ],
  "status_url": "/jobs/71125a92-b96e-42e7-afe8-5d43d6981c42",
  "research": null
}
```

Fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | UUID string | Job identifier. |
| `pipeline` | `flashcards`, `dataset`, or `research` | Selected pipeline. |
| `status` | `pending`, `running`, `completed`, or `failed` | Execution status. |
| `created_at` | ISO 8601 datetime | Submission time. |
| `started_at` | datetime or `null` | Worker start time. |
| `finished_at` | datetime or `null` | Completion/failure time. |
| `error` | string or `null` | Processing error when execution fails. |
| `artifacts` | array | Files currently available for download. |
| `status_url` | string | Relative polling URL. |
| `research` | object or `null` | Research-quality result; null for other pipelines and while research is running. |

## `POST /pipelines/flashcards`

Submit a UTF-8 text document for flashcard generation.

Request content type: `multipart/form-data`

| Form field | Type | Required | Default | Constraints |
|---|---|---:|---:|---|
| `file` | file | yes | — | Filename must end in `.txt`; maximum upload is 256 MiB. |
| `cards_per_chunk` | integer | no | `5` | 1–12. |
| `max_chunk_chars` | integer | no | `3000` | 500–4000. |

Example:

```bash
curl -X POST http://127.0.0.1:8000/pipelines/flashcards \
  -H "X-API-Key: $LOCAL_AI_API_KEY" \
  -F "file=@notes.txt" \
  -F "cards_per_chunk=5" \
  -F "max_chunk_chars=3000"
```

Response: `202 Accepted` with the common job response. Successful jobs normally
provide `flashcards.csv`, `flashcards.json`, and `source.json`.

## `POST /pipelines/dataset`

Submit a CSV file for validation, deterministic repair, cleaning, storage, and
an explicitly requested statistical analysis.

Request content type: `multipart/form-data`

| Form field | Type | Required | Default | Constraints |
|---|---|---:|---|---|
| `file` | file | yes | — | Filename must end in `.csv`; maximum upload is 256 MiB. |
| `date_order` | string | no | `dmy` | `dmy`, `mdy`, or `ymd`. |
| `trust_date_order` | boolean | no | `false` | Whether ambiguous dates may use `date_order`. |
| `record_mode` | string | no | `single_line` | `single_line` or `standard`. |
| `analysis_plan` | JSON string | no | `{"analyses":[]}` | Shape described below. |
| `interpret` | boolean | no | `true` | Ask local Qwen to interpret R results. |
| `source_profile` | JSON string | no | empty | Optional profile; overrides date and record fields. |

`analysis_plan` JSON shape:

```json
{
  "analyses": [
    {
      "test": "pearson",
      "columns": ["age", "score"]
    }
  ],
  "correction": "BH"
}
```

`test` may be `descriptive`, `pearson`, `spearman`, `chi_square`,
`independent_t`, `paired_t`, `anova`, `mann_whitney`, `wilcoxon`,
`kruskal_wallis`, `linear_regression`, or `logistic_regression`.
`correction` may be `BH`, `holm`, or `bonferroni`. Most tests require exactly
two distinct columns. Descriptive analysis accepts one or more columns;
regressions use the first column as the outcome followed by predictors.

`source_profile` JSON shape:

```json
{
  "source": "clinic_export",
  "date_order": "dmy",
  "trust_date_order": true,
  "record_mode": "single_line"
}
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/pipelines/dataset \
  -H "X-API-Key: $LOCAL_AI_API_KEY" \
  -F "file=@dataset.csv" \
  -F 'analysis_plan={"analyses":[{"test":"pearson","columns":["age","score"]}],"correction":"BH"}' \
  -F "interpret=true"
```

Response: `202 Accepted` with the common job response. Depending on validation
and analysis options, artifacts can include cleaned XLSX/Parquet data, a DuckDB
database, repair/quarantine records, structured statistical results, logs, and
an optional Qwen interpretation.

## `POST /pipelines/research`

Submit a research PDF for page-aware extraction, grounded evidence extraction,
quality assessment, and report synthesis.

Request content type: `multipart/form-data`

| Form field | Type | Required | Default | Constraints |
|---|---|---:|---|---|
| `file` | file | yes | — | Filename must end in `.pdf`; maximum upload is 256 MiB. |
| `max_chunk_chars` | integer | no | `3000` | 500–4000. |
| `document_type` | string | no | `auto` | `auto`, `empirical`, `review`, or `theoretical`. |
| `reading_order` | string | no | `auto` | `auto`, `single`, `two`, or `three`. |

Example:

```bash
curl -X POST http://127.0.0.1:8000/pipelines/research \
  -H "X-API-Key: $LOCAL_AI_API_KEY" \
  -F "file=@paper.pdf" \
  -F "document_type=auto" \
  -F "reading_order=auto"
```

Response: `202 Accepted` with the common job response. Once processing ends,
`research` has this additional shape:

```json
{
  "schema_version": "2.1",
  "status": "partial",
  "processing_status": "completed",
  "processing_error": null,
  "document_type": "empirical",
  "reasons": [],
  "missing_coverage": ["limitations"],
  "coverage": {
    "objective": true,
    "methods": true,
    "findings": true
  },
  "coverage_assessment": {
    "objective": "supported",
    "methods": "supported",
    "limitations": "uncertain"
  },
  "source_quality_issues": [],
  "accepted_records": 24,
  "rejected_attempts": 5,
  "selected_records": 9,
  "extraction_complete": true
}
```

Research `status` (`completed`, `partial`, or `failed`) measures report quality
and is separate from the top-level execution `status`. Coverage-assessment
values are `supported`, `not_reported`, `not_extracted`, `uncertain`, or
`not_applicable`.

Research artifacts may include `pages.json`, `passages.json`, `evidence.json`,
`rejected_evidence.json`, `synthesis.json`, `research_report.md`,
`research_quality.json`, `research_diagnostics.json`, `research_events.jsonl`,
and `research_limited_overview.md`. Checkpoint artifacts remain available when
processing fails.

## `GET /jobs`

Return up to the 100 most recently stored jobs, newest first.

Request body: none.

Response: `200 OK`

```json
[
  {
    "id": "71125a92-b96e-42e7-afe8-5d43d6981c42",
    "pipeline": "research",
    "status": "failed",
    "created_at": "2026-10-03T10:00:00Z",
    "started_at": "2026-10-03T10:00:01Z",
    "finished_at": "2026-10-03T10:30:00Z",
    "error": "RuntimeError: ...",
    "artifacts": [],
    "status_url": "/jobs/71125a92-b96e-42e7-afe8-5d43d6981c42",
    "research": null
  }
]
```

Each array item follows the common job response shape.

## `GET /jobs/{job_id}`

Return the current state, downloadable artifacts, and—when applicable—research
quality for one job.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `job_id` | UUID | ID returned by a pipeline submission. |

Request body: none.

Response: `200 OK` with the common job response.

Errors: `404 Not Found` with `{"detail":"Unknown job"}`; malformed UUIDs return
FastAPI’s `422 Unprocessable Entity` validation response.

## `GET /jobs/{job_id}/artifacts/{filename}`

Download an artifact explicitly associated with the job. Arbitrary filesystem
paths cannot be requested.

Path parameters:

| Name | Type | Meaning |
|---|---|---|
| `job_id` | UUID | Existing job ID. |
| `filename` | string | Exact filename listed in the job’s `artifacts` array. |

Request body: none.

Response: `200 OK` with the file bytes and an appropriate content type and
`Content-Disposition` filename.

Errors: `404 Not Found` with `{"detail":"Unknown job"}` or
`{"detail":"Unknown artifact"}`.

## `GET /health`

Check the API and locally installed processing dependencies.

Request body: none.

Response: `200 OK`

```json
{
  "api": "ok",
  "qwen3_8b_available": true,
  "Rscript": true,
  "worker_count": 1
}
```

This endpoint reports availability only; it does not run an inference or an R
analysis.

## `POST /chat/stream`

Stream a stateless Qwen chat response through FastAPI. The client must send the
conversation history needed for the model to understand the current turn. The
backend owns the system prompt, model configuration, and local Ollama connection.
The client must not send `system` messages or model settings.

Request content type: `application/json`

Successful response content type: `application/x-ndjson`

Request body:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "What date format do I prefer?"
    }
  ],
  "memories": [
    {
      "id": "date-format",
      "content": "Massa prefers UK date formatting."
    }
  ]
oy-content characters maximum. |
| Unknown fields | Rejected. |

Successful streams are newline-delimited JSON events:

```json
{"type":"meta","model":"qwen3:8b","assistant":"Shaka"}
{"type":"memory_save","content":"Massa prefers UK date formatting."}
{"type":"token","content":"Gradient"}
{"type":"token","content":" descent"}
{"type":"done"}
```

Event types:

| Type | Shape | Meaning |
|---|---|---|
| `meta` | `{"type":"meta","model":"qwen3:8b","assistant":"Shaka"}` | Identifies assistant identity and underlying model. |
| `memory_save` | `{"type":"memory_save","content":"..."}` | Authoritative request for the client to persist an explicit local memory. |
| `token` | `{"type":"token","content":"..."}` | Append streamed assistant text. |
| `done` | `{"type":"done"}` | Assistant turn completed successfully. |
| `error` | `{"type":"error","detail":"..."}` | Safe stream error, possibly after partial output. |

The client owns persistent memories. Chat history remains nonpersistent. Natural
language token text such as "I'll remember that" is not authoritative and must
not be persisted unless a structured `memory_save` event is present.

Pre-stream errors include:

| Status | Cause |
|---:|---|
| `401` | Missing or invalid API key. |
| `409` | Shared local AI resource is busy with another heavy task. |
| `422` | Chat validation failed. |
| `502` | Unexpected or malformed pre-stream Ollama response. |
| `503` | Ollama unreachable or `qwen3:8b` unavailable. |

## Browser and schema routes

### `GET /`

Returns a redirect to `/docs`.

### `GET /docs`

Returns the self-hosted Swagger UI. It can be used to submit all three pipeline
forms and inspect job responses from a browser.

### `GET /openapi.json`

Returns FastAPI’s generated OpenAPI schema as JSON.

`/static/swagger/*` serves local Swagger UI assets and is not an application API.

## Common errors

Application errors use FastAPI’s normal detail shape:

```json
{
  "detail": "Upload a .pdf file"
}
```

Common statuses:

| Status | Cause |
|---:|---|
| `401` | Missing or invalid `X-API-Key` when a key is configured. |
| `403` | Remote request while no API key is configured. |
| `404` | Unknown job or artifact. |
| `413` | Upload exceeds 256 MiB. |
| `422` | Empty file, wrong extension, invalid form value, invalid JSON field, or malformed UUID. |

FastAPI/Pydantic field-validation errors use an array under `detail`, containing
locations, messages, and error types.
