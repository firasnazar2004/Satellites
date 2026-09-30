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

Each successful run produces:

- `cleaned.parquet` — whitespace/missing values normalized and safe types cast
- `dataset_report.json` — schema, missing counts, unique counts, and duplicates
- `csv_inspection.json` — encoding, delimiter, headers, and row-width checks
- `job.json` — job lifecycle and artifact metadata

Dates are stored as real Parquet date values. UK `DD/MM/YYYY` display formatting
will be applied when XLSX output is introduced; display formatting is not stored
inside Parquet. Exact duplicate rows are reported but retained because repeated
observations can be legitimate data.

Step 4 deliberately does not repair rows with too many or too few fields. Such
files fail safely and retain `csv_inspection.json` for the deterministic repair
work in Step 5. Step 4 currently accepts UTF-8 input and requires a header row.

## Checks

Run the fast tests without loading Ollama:

```bash
python -m unittest discover -v
```

Run a real local-model example:

```bash
python -m app flashcards examples/photosynthesis.txt --cards-per-chunk 3
```
