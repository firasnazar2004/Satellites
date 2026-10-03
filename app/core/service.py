"""SQLite-backed job state, immutable uploads, and one background worker."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.core.execution import execute
from app.core.jobs import create_job, run_job, _save_job
from app.models.job import Job, JobStatus, PipelineType


class JobService:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "jobs.sqlite3"
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            for jid, payload in db.execute("SELECT id,payload FROM jobs").fetchall():
                job = Job.model_validate_json(payload)
                if job.status in {JobStatus.PENDING, JobStatus.RUNNING}:
                    job.status = JobStatus.FAILED
                    job.error = (
                        "Server stopped before job completion; resubmit the upload"
                    )
                    job.finished_at = datetime.now(UTC)
                    _save_job(job)
                    db.execute(
                        "UPDATE jobs SET payload=? WHERE id=?",
                        (job.model_dump_json(), jid),
                    )
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, job):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?)",
                (job.id, job.model_dump_json()),
            )

    def submit(self, pipeline: PipelineType, source: Path, options: dict):
        job = create_job(pipeline, source, jobs_root=self.root / "jobs")
        with source.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        (job.output_dir / "source.json").write_text(
            json.dumps(
                {
                    "filename": source.name,
                    "sha256": digest,
                    "bytes": source.stat().st_size,
                },
                indent=2,
            )
        )
        self.save(job)
        self.executor.submit(self.work, job, options)
        return job

    def work(self, job, options):
        def processor(source, output):
            self.save(job)  # run_job has set RUNNING before invoking this.
            return execute(job.pipeline.value, source, output, options) + [
                output / "source.json"
            ]

        try:
            run_job(job, processor)
        except Exception:
            pass  # run_job records the failure and worker.log preserves the traceback.
        finally:
            self.save(job)

    def get(self, jid):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM jobs WHERE id=?", (str(jid),)
            ).fetchone()
        return Job.model_validate_json(row[0]) if row else None

    def list(self):
        with self.connect() as db:
            return [
                Job.model_validate_json(row[0])
                for row in db.execute(
                    "SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 100"
                )
            ]

    def close(self):
        self.executor.shutdown(wait=True)
