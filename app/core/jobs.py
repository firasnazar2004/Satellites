"""Minimal, pipeline-independent job lifecycle management."""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.models.job import Job, JobStatus, PipelineType


Processor = Callable[[Path, Path], Sequence[Path]]
JOB_RECORD_NAME = "job.json"


def create_job(
    pipeline: PipelineType,
    input_path: Path,
    *,
    jobs_root: Path = Path("outputs/jobs"),
) -> Job:
    """Create a pending job and its isolated output directory."""

    input_path = input_path.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    job_id = str(uuid4())
    job = Job(
        id=job_id,
        pipeline=pipeline,
        input_path=input_path,
        output_dir=jobs_root.expanduser().resolve() / job_id,
    )
    job.output_dir.mkdir(parents=True, exist_ok=False)
    _save_job(job)
    return job


def run_job(job: Job, processor: Processor) -> Job:
    """Run a processor while recording lifecycle state and produced files."""

    if job.status is not JobStatus.PENDING:
        raise ValueError(f"Job {job.id} cannot run from status {job.status}")

    job.status = JobStatus.RUNNING
    job.started_at = datetime.now(UTC)
    _save_job(job)

    try:
        artifacts = [
            path.resolve() for path in processor(job.input_path, job.output_dir)
        ]
        missing = [path for path in artifacts if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Processor reported missing artifacts: {missing}")

        job.artifacts = artifacts
        job.status = JobStatus.COMPLETED
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        job.finished_at = datetime.now(UTC)
        _save_job(job)

    return job


def _save_job(job: Job) -> None:
    record_path = job.output_dir / JOB_RECORD_NAME
    temporary = record_path.with_suffix(".json.tmp")
    temporary.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(record_path)
