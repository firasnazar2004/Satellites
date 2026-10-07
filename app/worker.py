"""One disposable pipeline process; input files and prompts are data only."""

import json
import sys
import traceback
import resource
import time
from pathlib import Path


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    source = Path(request["input"])
    output = Path(request["output"])
    started = time.monotonic()
    try:
        if request["pipeline"] == "dataset":
            from app.pipelines.dataset_full import process_dataset as processor
        elif request["pipeline"] == "flashcards":
            from app.pipelines.flashcards import process_flashcard_file as processor
        elif request["pipeline"] == "research":
            from app.pipelines.research import process_research_file as processor
        else:
            raise ValueError("Unsupported pipeline")
        artifacts = processor(source, output, **request["options"])
        metrics = output / "runtime.json"
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024
        metrics.write_text(
            json.dumps(
                {
                    "elapsed_seconds": time.monotonic() - started,
                    "python_peak_rss_bytes": rss,
                    "note": "Python process only; excludes Ollama GPU memory and R subprocess",
                },
                indent=2,
            )
        )
        artifacts.append(metrics)
        (output / "artifacts.json").write_text(
            json.dumps([str(p.resolve()) for p in artifacts])
        )
    except Exception as exc:
        (output / "error.txt").write_text(
            f"{type(exc).__name__}: {exc}", encoding="utf-8"
        )
        traceback.print_exc()
        return 1
    finally:
        try:
            from app.core.llm import unload_models

            unload_models()
        except Exception as exc:
            print(f"Model cleanup warning: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
