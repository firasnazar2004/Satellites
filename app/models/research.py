"""Versioned research contracts: the application owns source text and citations."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal["empirical", "review", "theoretical", "unknown"]
Section = Literal["front_matter", "abstract", "introduction", "methods", "results",
                  "discussion", "conclusions", "limitations", "references",
                  "appendices", "excluded", "unknown"]
Category = Literal["metadata", "objective", "study_design", "population",
                   "sample_size", "denominator", "percentage", "test_statistic",
                   "p_value", "confidence_interval", "effect_size",
                   "diagnostic_accuracy", "finding", "limitation", "conclusion"]
Origin = Literal["current_study", "cited_study", "background"]


class SourcePassage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    page: int
    section: Section
    kind: Literal["text", "table"] = "text"
    text: str
    raw_text: str
    bbox: tuple[float, float, float, float]
    line_ids: list[str] = Field(default_factory=list)
    table_id: str | None = None
    context_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    passage_id: str = Field(min_length=1, max_length=40)
    category: Category
    # A short literal measure/phrase, never a model-written quotation or calculation.
    value: str = Field(min_length=1, max_length=240)
    origin: Origin
    attribution: str | None = Field(default=None, max_length=160)
    importance: Literal["primary", "secondary"] = "secondary"


class ExtractionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: list[EvidenceProposal] = Field(default_factory=list, max_length=6)


class BibliographicField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["title", "authors", "year", "journal", "doi"]
    passage_id: str = Field(max_length=40)
    value: str = Field(min_length=1, max_length=240)


class DocumentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: DocumentType = "unknown"
    type_source_ids: list[str] = Field(default_factory=list, max_length=3)
    metadata: list[BibliographicField] = Field(default_factory=list, max_length=10)


class GroundedEvidence(EvidenceProposal):
    id: str
    source: str
    page: int
    section: Section
    source_kind: Literal["text", "table"] = "text"
    quote: str
    value_start: int
    value_end: int
    context_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "2.1"
    status: Literal["completed", "partial", "failed"]
    processing_status: Literal["completed", "failed"] = "completed"
    processing_error: str | None = None
    document_type: DocumentType = "unknown"
    reasons: list[str] = Field(default_factory=list)
    missing_coverage: list[str] = Field(default_factory=list)
    coverage: dict[str, bool] = Field(default_factory=dict)
    coverage_assessment: dict[str, Literal[
        "supported", "not_reported", "not_extracted", "uncertain", "not_applicable"
    ]] = Field(default_factory=dict)
    source_quality_issues: list[str] = Field(default_factory=list)
    accepted_records: int = 0
    rejected_attempts: int = 0
    selected_records: int = 0
    extraction_complete: bool = False


class CitedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=8, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    source_ids: list[str] = Field(min_length=1, max_length=6)


class ResearchNarrative(BaseModel):
    """Readable paraphrase; Python validates references and renders numbers."""
    model_config = ConfigDict(extra="forbid")
    introduction: CitedClaim | None = None
    methods_scope: list[CitedClaim] = Field(default_factory=list, max_length=5)
    key_findings: list[CitedClaim] = Field(default_factory=list, max_length=8)
    statistical_information: list[CitedClaim] = Field(default_factory=list, max_length=6)
    conclusion: list[CitedClaim] = Field(default_factory=list, max_length=3)


class LimitedOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    overview: str = Field(min_length=10, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=4)


class ArtifactLink(BaseModel):
    name: str
    url: str


class JobResponse(BaseModel):
    """Execution status is unchanged; research quality is a separate contract."""
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


# Legacy shapes retained only for reading/testing v1 artifacts. The new pipeline
# never asks a model to emit long verbatim quotations or uses the old synthesis.


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal[
        "metadata",
        "study_design",
        "sample_size",
        "population",
        "finding",
        "effect_size",
        "confidence_interval",
        "p_value",
        "limitation",
        "conclusion",
    ]
    quote: str = Field(min_length=5, max_length=1200)
    value: str = Field(min_length=1, max_length=600)


class EvidenceBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: list[Evidence] = Field(max_length=8)


class Synthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    main_findings: list[str] = Field(max_length=8)
    methods_and_population: list[str] = Field(max_length=6)
    limitations: list[str] = Field(max_length=6)
