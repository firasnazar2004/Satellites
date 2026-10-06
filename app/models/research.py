"""Compatibility fields retained by the generic job response contract."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal[
    "empirical", "review", "theoretical", "theoretical_with_experiments", "mixed", "unknown"
]


class StageOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["completed", "partial", "failed", "not_run"] = "not_run"
    reason: str | None = None
    input_ids: list[str] = Field(default_factory=list, max_length=50)
    output_ids: list[str] = Field(default_factory=list, max_length=50)


class ResearchOutcome(BaseModel):
    """Legacy optional job response field retained for API compatibility."""

    model_config = ConfigDict(extra="forbid")
    schema_version: str = "2.4"
    status: Literal["completed", "partial", "failed"]
    processing_status: Literal["completed", "failed"] = "completed"
    processing_error: str | None = None
    document_type: DocumentType = "unknown"
    reasons: list[str] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)
    coverage: dict[str, bool] = Field(default_factory=dict)
    coverage_by_stage: dict[str, dict[str, bool]] = Field(default_factory=dict)
    coverage_assessment: dict[str, Literal[
        "supported", "not_reported", "not_extracted", "uncertain", "not_applicable"
    ]] = Field(default_factory=dict)
    source_quality_issues: list[str] = Field(default_factory=list)
    accepted_records: int = 0
    rejected_attempts: int = 0
    selected_records: int = 0
    extraction_complete: bool = False
    report_availability: Literal["available", "partial", "unavailable"] = "unavailable"
    report_kind: Literal[
        "validated_report", "partial_report", "limited_overview", "unavailable"
    ] = "unavailable"
    stage_outcomes: dict[str, StageOutcome] = Field(default_factory=dict)


class ArtifactLink(BaseModel):
    name: str
    url: str


class JobResponse(BaseModel):
    """Generic job response; research remains null for non-research jobs."""

    id: str
    pipeline: str
    status: Literal["pending", "running", "completed", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    artifacts: list[ArtifactLink]
    status_url: str
    research: ResearchOutcome | None = Field(default=None, description=
        "Research quality, independent of execution status. Null while processing, "
        "for non-research jobs, and for legacy jobs without quality artifacts.")
