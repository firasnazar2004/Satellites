"""Models shared by all processing jobs."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class PipelineType(StrEnum):
    FLASHCARDS = "flashcards"
    DATASET = "dataset"
    # Also retained for persisted historical jobs.
    RESEARCH = "research"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(BaseModel):
    """Metadata and lifecycle state for one pipeline execution."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    pipeline: PipelineType
    input_path: Path
    output_dir: Path
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    artifacts: list[Path] = Field(default_factory=list)
    error: str | None = None
