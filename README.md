# Local LLM Data Assistant

Three local pipelines through a CLI and FastAPI's interactive Swagger UI. Qwen3:8b
generates language; Python validates and exports it; **R alone calculates
statistics**. No paid model API or cloud processing is used.

## Start and test in the browser

From this project directory, with Ollama running and `qwen3:8b` installed:

```bash
source .venv/bin/activate
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --workers 1
```

Open **http://127.0.0.1:8000/docs**. All Swagger assets are served locally.

1. Expand a `POST /pipelines/...` endpoint and click **Try it out**.
2. Choose your TXT, CSV, or PDF, set the options, and click **Execute**.
3. Copy the `id` from the **202** response (queued, not finished).
4. Poll `GET /jobs/{job_id}` until `completed` or `failed`.
5. Download the returned artifact URLs, or use the artifact-download endpoint.

`GET /jobs` lists the latest 100 jobs. `/health` checks model availability and the
R executable; the smoke test verifies actual execution. Outputs/uploads live in
`outputs/api/`. Use one Uvicorn worker and avoid `--reload` during jobs.

Loopback testing needs no key. For authenticated use, set `LOCAL_AI_API_KEY`
before startup and enter it in Swagger's **Authorize** dialog (`X-API-Key`).
Non-loopback requests are rejected without a configured key. Authenticated
downloads work through Swagger; bare browser links do not attach the key.
Never expose this service or Ollama publicly. VPN deployment remains V1 work.

## Dependencies

Python 3.13 and the existing `.venv` are supported:

```bash
python -m pip install -r requirements.txt
brew install r
Rscript --vanilla -e 'install.packages("jsonlite", repos="https://cloud.r-project.org")'
Rscript --vanilla -e 'library(jsonlite); sessionInfo()'
ollama list
```

Validated with R 4.6.1, jsonlite 2.0.0, Ollama 0.15.6, and local Qwen model ID
`500a1f067a9f`. If older Apple Clang rejects R's `-std=gnu23` when compiling
jsonlite, use the checked-in compatibility override:

```bash
R_MAKEVARS_USER="$PWD/config/R-Makevars" Rscript --vanilla -e 'install.packages("jsonlite", repos="https://cloud.r-project.org")'
```

Installation/model downloads need internet; processing does not. Swagger UI
5.33.0 is vendored with its license in `app/static/swagger/`; no Node runtime or
frontend build is needed.

## Dataset pipeline

```bash
python -m app dataset path/to/data.csv
python -m app dataset path/to/data.csv --analysis-plan config/analysis.example.json
python -m app dataset path/to/data.csv --profile config/profiles/uk_export.json
python -m app dataset path/to/data.csv --no-interpret
```

Swagger's `analysis_plan` and `source_profile` fields accept JSON **contents**, not
file paths. Edit example column names to match your CSV. An empty analysis list
defaults to descriptive statistics on up to 20 numeric columns, excluding names
ending in `id`. Categorical-only datasets still export; default statistics are
explicitly skipped.

```json
{
  "analyses": [
    {"test": "descriptive", "columns": ["age", "score"]},
    {"test": "pearson", "columns": ["age", "score"]}
  ],
  "correction": "BH"
}
```

| Test | `columns`, in order |
| --- | --- |
| `descriptive` | One or more numeric columns |
| `pearson`, `spearman` | Numeric x, numeric y |
| `chi_square` | Category x, category y |
| `independent_t`, `mann_whitney` | Numeric measurement, two-level group |
| `paired_t`, `wilcoxon` | Numeric before, numeric after, paired by row |
| `anova`, `kruskal_wallis` | Numeric measurement, group |
| `linear_regression` | Numeric outcome, then predictors |
| `logistic_regression` | Outcome containing both 0 and 1, then predictors |

Tests are two-sided with 95% intervals where supported. Independent t-tests use
Welch's test; rank tests use asymptotic calculations. Complete cases are selected
**per analysis**, including multi-column descriptive requests. Separate descriptive
requests give per-column missingness handling. R records exclusions and sample size.

Effect sizes include correlations, Cramer's V, Cohen's d/dz, rank-biserial
correlation, eta/epsilon squared, and model R-squared/pseudo-R-squared. Intervals
cover means, Pearson correlation, t-test differences, rank-test location estimates,
and regression coefficients/odds ratios where supported; not every effect size
has an interval. Inspect each result's `warnings` and `error`: a completed job can
contain an explicitly failed individual test. Assumptions are not certified.

`BH`, `holm`, or `bonferroni` correct requested-test p-values; coefficient p-values
form a separate family within each regression. No autonomous test selection.
Qwen receives compact R results, never raw rows. Python renders the numerical
results separately; model prose containing digits is rejected/retried up to three
times. Qualitative prose still needs human review.

### Repair and dates

UTF-8/BOM CSV with a header is required. A schema is inferred from conforming rows;
repairs are accepted only when **one** candidate satisfies it. Missing required
values, invalid types, duplicate rows/keys, unusual numeric values, ambiguous
dates, and competing repairs are quarantined. This conservative heuristic does
not prove intended values. `VALID` does not mean semantically verified, and
quarantined rows are not necessarily wrong. Review exclusion bias before analysis.

Default `record_mode=single_line` isolates malformed quoting per physical line.
Use `standard` for correctly quoted multiline fields; that mode fails on invalid
quoting rather than guessing record boundaries.

Dates like `03/04/2026` are quarantined unless the source convention is trusted.
Profiles declare `source`, `date_order` (`dmy`, `mdy`, `ymd`), `trust_date_order`,
and `record_mode`; they override individual options. Dates remain typed in Parquet
and DuckDB and are real Excel dates displayed as `dd/mm/yyyy`. Text cells and
headers cannot become Excel formulas.

Outputs include `cleaned.parquet`, `dataset.duckdb` (table `cleaned`),
`cleaned.xlsx`, `statistics.json`, `interpretation.json`, `statistical_report.md`,
`dataset_summary.json`, schema/quality reports, `repaired.csv`, `row_status.csv`,
`repair_log.json`, `quarantine.csv`, and R logs. XLSX sheets split at Excel's row
limit. With no accepted rows, statistics are skipped.

## Research pipeline

```bash
python -m app research path/to/paper.pdf
```

Research schema v2.1 uses pdfplumber word geometry, conservative spacing/line-break
normalization, section recognition, and ruled-table extraction. Raw text, cells,
coordinates, normalized text, and application-assigned passage IDs remain auditable.
Continuation pages in front-matter lists stay excluded; identifiable second-row
table headings are carried into data-row passages. Empirical extraction skips most
literature background while retaining its opening context and explicit objectives.
Qwen selects passage IDs and short literal values; Python retrieves the quotations
and checks measure labels, category shapes, attribution, and exact numeric support.
Corrective extraction attempts are bounded. References/front matter are excluded
from findings; cited studies are distinguished from the document's own work.
Supported document classification is retained even when optional bibliographic
fields are rejected. Numeric values must appear in the raw local passage, and
table measures remain provisional until their original headings are reviewed.

Global ranking and deduplication select validated evidence for a bounded Qwen
synthesis. Python checks evidence and passage IDs in every narrative claim and
renders all numbers from their validated source records, including source wording,
units and page citations. The Markdown report has introduction, methods, findings,
statistical information and conclusion sections. Empirical, review, and theoretical
documents have different expectations; unreported optional fields are marked
uncertain rather than treated as absent. Layout/type overrides are available:

```bash
python -m app research path/to/paper.pdf --document-type empirical --reading-order two
```

Inspect research_quality.json for complete, partial, or failed quality, separate
processing status, coverage assessment and source-quality caveats. These assess
extraction and coverage, not scientific truth. API job status remains execution
status; research.status is report quality. A finished run can return job status
completed with research quality partial or failed. Parser, model, or synthesis
processing failures keep job status failed. Whenever quality is incomplete, the
pipeline attempts a separately labelled, at-most-two-sentence orientation from
readable text. It is not a validated summary. If text or local Qwen is unavailable,
the overview artifact explains the fallback. CLI exit codes are 0 for completed
quality, 2 for partial or failed quality, and 1 for execution failure.

Artifacts: `pages.json`, `passages.json`, `evidence.json`,
`rejected_evidence.json`, `synthesis.json`, `research_report.md`,
`research_quality.json`, `research_diagnostics.json`, `research_events.jsonl`, and
`research_limited_overview.md` when quality is incomplete or processing fails.
Existing checkpoints are downloadable even for failed jobs. Legacy job artifacts
are not migrated; their API `research` field is null.

OCR remains excluded. Unruled or complex tables, ambiguous headings/layouts and
semantic attribution need human review. Model citations are checked against
supplied validated IDs; exact mention does not prove semantic support. See
[research contracts, limitations and verification](docs/RESEARCH_PIPELINE.md).
The research regression suite and read-only dissertation extraction checks pass.
A live Qwen profiling attempt could not connect to local Ollama in this session;
re-run the API pipeline with Ollama available to evaluate the final report.

## Flashcards

```bash
python -m app flashcards path/to/notes.txt --cards-per-chunk 5
```

TXT cleanup and paragraph/word chunking precede serial Qwen calls. Pydantic
validates JSON, normalized duplicate questions are removed, and Python writes
`flashcards.json` and `flashcards.csv` (Front, Back, Topic, Difficulty, Source).
Map fields and handle the header when importing into Anki. Count is per chunk,
not a document-wide ranking target. Semantic deduplication, cloze, and independent
factual verification are future work; review generated cards.

## Runtime and failures

- One disposable subprocess per heavy job; a cross-process lock serializes
  CLI/API. Dataset stages unload Ollama, finish R, release frames, then call Qwen.
  Models are unloaded at job completion. Avoid unrelated simultaneous Ollama work.
- Qwen context: 4096 tokens; input chunks: 500–4000 characters. Reduce chunk size
  for dense/multilingual inputs or truncated JSON. Generation timeout: 300 seconds;
  selected transient server errors retry up to three attempts.
- R timeout: 300 seconds. Job timeout: 7200 seconds (`LOCAL_AI_JOB_TIMEOUT`).
  API upload limit: 256 MiB. Storage root: `LOCAL_AI_STORAGE`, default `outputs/api`.
- API uploads are isolated read-only copies with SHA-256 metadata. SQLite tracks
  jobs. `job.json`, `request.json`, `worker.log`, and `runtime.json` aid diagnosis.
  CLI jobs reference the supplied source file and have isolated output folders.
- Pending/running API jobs interrupted by restart are marked failed; resubmit
  explicitly. Automatic resume, backups, and crash-proof scheduling remain V1.
- Available failure diagnostics can be downloaded at
  `/jobs/{id}/artifacts/worker.log` and `.../error.txt`. Partial artifacts on disk
  after failure are not successful deliverables.

## Verification

```bash
python -m unittest discover -v
python scripts/mvp_smoke.py
python scripts/verify_dataset.py
```

Regression tests need R/jsonlite but mock model calls. The smoke test needs the
running API and real Qwen: it creates synthetic inputs, submits all three jobs,
downloads artifacts, and validates them. The dataset script compares your faulty
fixture to its expected data (if present) and runs a 100,000-row check. Results are
in `outputs/verification/` and `outputs/dataset-verification/`.

New versioned tests live in `checks/`, preserving your existing `tests/` ignore
policy and private fixtures. Optional tooling is in `requirements-dev.txt`.

See [the PDF specification review](docs/MVP_SPEC_REVIEW.md) for coverage and
limitations. This is the processing/API MVP, **not an unattended production server**.
