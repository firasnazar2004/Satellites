# Local LLM Data Assistant

A completely local processing project using Ollama and `qwen3:8b`. The current
MVP implements the shared job lifecycle, TXT-to-flashcards pipeline, and basic
CSV ingestion and cleaning.

## Generate flashcards

Start Ollama, activate the existing virtual environment, and pass the command
the path to any UTF-8 text file:

```bash
python -m app flashcards path/to/notes.txt
```

Useful options:

```bash
python -m app flashcards path/to/notes.txt \
  --cards-per-chunk 5 \
  --max-chunk-chars 4000 \
  --model qwen3:8b
```

Each run creates `outputs/jobs/<job-id>/` containing:

- `flashcards.csv` — columns: Front, Back, Topic, Difficulty, Source
- `flashcards.json` — the validated structured model output
- `job.json` — status, timestamps, input, artifacts, and any error

The input is cleaned and split on paragraph boundaries. Chunks are processed
serially to suit the 8 GB machine. Python validates every Qwen response with
Pydantic, removes duplicate questions, and writes the CSV; Qwen never writes
CSV directly.

## Clean a dataset

Pass a UTF-8 CSV with a header row to the dataset command:

```bash
python -m app dataset path/to/data.csv
```

The default date order is UK day-month-year. Override it for a source that uses
a different convention:

```bash
python -m app dataset path/to/data.csv --date-order mdy
```

Dates such as `03/04/2026` are quarantined by default because both DMY and MDY
interpretations are valid. If a source profile confirms its convention, opt in
to resolving those values:

```bash
python -m app dataset path/to/data.csv --date-order dmy --trust-date-order
```

Each successful run produces:

- `cleaned.parquet` — whitespace/missing values normalized and safe types cast
- `dataset_report.json` — schema, missing counts, unique counts, and duplicates
- `csv_inspection.json` — encoding, delimiter, headers, and row-width checks
- `repaired.csv` — all `VALID` and deterministically `REPAIRED` rows
- `quarantine.csv` — `AMBIGUOUS` rows with reasons and original source text
- `repair_log.json` — repair counts, inferred schema, and changed-row details
- `row_status.csv` — one `VALID`, `REPAIRED`, or `AMBIGUOUS` result per source row
- `job.json` — job lifecycle and artifact metadata

Dates are stored as real Parquet date values. UK `DD/MM/YYYY` display formatting
will be applied when XLSX output is introduced; display formatting is not stored
inside Parquet. Exact duplicate rows are reported but retained because repeated
observations can be legitimate data.

Step 5 evaluates malformed rows against a schema inferred from the conforming
majority. It applies a repair only when exactly one candidate satisfies that
schema. Missing source values, duplicate keys, exact duplicates, invalid types,
outliers, and multiple valid alignments are quarantined instead of guessed.

The MVP repair reader accepts UTF-8 input with a header and assumes one source
record per physical line. Valid multiline quoted fields are a later extension.

## Checks

Run the fast tests without loading Ollama:

```bash
python -m unittest discover -v
```

Run a real local-model example:

```bash
python -m app flashcards examples/photosynthesis.txt --cards-per-chunk 3
```
