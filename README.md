# Local LLM Data Assistant

A completely local processing project using Ollama and `qwen3:8b`. The current
MVP implements the shared job lifecycle and the TXT-to-flashcards pipeline.

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

## Checks

Run the fast tests without loading Ollama:

```bash
python -m unittest discover -v
```

Run a real local-model example:

```bash
python -m app flashcards examples/photosynthesis.txt --cards-per-chunk 3
```
