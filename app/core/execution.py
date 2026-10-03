"""Process isolation releases pipeline memory and a file lock serializes CLI/API jobs."""

import fcntl
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def execute(pipeline: str, source: Path, output: Path, options: dict) -> list[Path]:
    config = output / "request.json"
    config.write_text(
        json.dumps(
            {
                "pipeline": pipeline,
                "input": str(source.resolve()),
                "output": str(output.resolve()),
                "options": options,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    lock_dir = ROOT / "outputs"
    lock_dir.mkdir(exist_ok=True)
    with (
        (lock_dir / "heavy-worker.lock").open("a") as lock,
        (output / "worker.log").open("w") as log,
    ):
        fcntl.flock(lock, fcntl.LOCK_EX)
        process = subprocess.Popen(
            [sys.executable, "-m", "app.worker", str(config.resolve())],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={
                **os.environ,
                "POLARS_MAX_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            },
        )
        try:
            code = process.wait(
                timeout=int(os.environ.get("LOCAL_AI_JOB_TIMEOUT", "7200"))
            )
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    if code:
        message = (
            (output / "error.txt").read_text()
            if (output / "error.txt").exists()
            else "Pipeline process failed; see worker.log"
        )
        raise RuntimeError(message)
    return [Path(p) for p in json.loads((output / "artifacts.json").read_text())] + [
        config,
        output / "worker.log",
    ]
