"""Tests for the generic job lifecycle."""

import json
import tempfile
import unittest
from pathlib import Path

from app.core.jobs import JOB_RECORD_NAME, create_job, run_job
from app.models.job import JobStatus, PipelineType


class JobLifecycleTests(unittest.TestCase):
    def test_successful_job_records_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "notes.txt"
            input_path.write_text("source text", encoding="utf-8")

            job = create_job(
                PipelineType.FLASHCARDS,
                input_path,
                jobs_root=root / "jobs",
            )

            def processor(source: Path, output_dir: Path) -> list[Path]:
                artifact = output_dir / "result.txt"
                artifact.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
                return [artifact]

            result = run_job(job, processor)
            record = json.loads(
                (result.output_dir / JOB_RECORD_NAME).read_text(encoding="utf-8")
            )

            self.assertEqual(result.status, JobStatus.COMPLETED)
            self.assertEqual(result.artifacts, [result.output_dir / "result.txt"])
            self.assertEqual(record["status"], "completed")
            self.assertIsNotNone(record["started_at"])
            self.assertIsNotNone(record["finished_at"])

    def test_failed_job_records_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "notes.txt"
            input_path.write_text("source text", encoding="utf-8")
            job = create_job(
                PipelineType.FLASHCARDS,
                input_path,
                jobs_root=root / "jobs",
            )

            def processor(_source: Path, _output_dir: Path) -> list[Path]:
                raise RuntimeError("processing broke")

            with self.assertRaisesRegex(RuntimeError, "processing broke"):
                run_job(job, processor)

            record = json.loads(
                (job.output_dir / JOB_RECORD_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["error"], "RuntimeError: processing broke")


if __name__ == "__main__":
    unittest.main()
