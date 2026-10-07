"""Versioned, auditable contracts for single-paper research analysis."""
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE_CAPTION = "table_caption"
    TABLE = "table"
    FIGURE_CAPTION = "figure_caption"
    FOOTNOTE = "footnote"
    OTHER = "other"


class SectionPath(StrictModel):
    parts: list[str] = Field(default_factory=list)
    role: Literal["body", "references"] = "body"

    def __str__(self) -> str:
        return " > ".join(self.parts)


class SourceBlock(StrictModel):
    block_id: str
    page: int = Field(ge=1)
    order: int = Field(ge=0)
    block_type: BlockType
    raw_text: str
    normalized_text: str
    section_path: SectionPath
    previous_block_id: str | None = None
    next_block_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    table_id: str | None = None
    numeric_uncertain: bool = False


class TableCell(StrictModel):
    row_label: str
    column_label: str
    value: str
    source_refs: list[str]


class TableStructure(StrictModel):
    table_id: str
    page: int = Field(ge=1)
    caption: str = ""
    column_labels: list[str] = Field(default_factory=list)
    row_labels: list[str] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    uncertain: bool = False


class PDFExtractionMetadata(StrictModel):
    extraction_method: str = "pdfplumber"
    page_count: int
    pages_with_text: int
    characters_by_page: list[int]
    empty_pages: list[int] = Field(default_factory=list)
    suspicious_pages: list[int] = Field(default_factory=list)
    tables_detected: int = 0
    headings_detected: int = 0
    numeric_uncertain_blocks: list[str] = Field(default_factory=list)


class ResearchSourceMap(StrictModel):
    schema_version: Literal[1] = 1
    source_filename: str
    metadata: PDFExtractionMetadata
    blocks: list[SourceBlock]
    tables: list[TableStructure] = Field(default_factory=list)


class ContextWindow(StrictModel):
    window_id: str
    section_path: SectionPath
    source_refs: list[str]
    previous_context_refs: list[str] = Field(default_factory=list)
    next_context_refs: list[str] = Field(default_factory=list)
    rendered_text: str


class DocumentTraits(StrictModel):
    has_human_participants: bool = False
    has_dataset: bool = False
    has_experiments: bool = False
    has_formal_model: bool = False
    has_intervention: bool = False
    has_statistical_results: bool = False
    has_tables: bool = False
    has_explicit_limitations: bool = False


class DocumentProfile(StrictModel):
    schema_version: Literal[1] = 1
    primary_kind: Literal["empirical", "theoretical", "methods", "review", "meta_analysis", "case_study", "mixed", "unknown"] = "unknown"
    traits: DocumentTraits = Field(default_factory=DocumentTraits)
    evidence_refs: list[str] = Field(default_factory=list)


EvidenceType = Literal["research_objective", "research_question", "hypothesis", "contribution", "theory_or_model", "population", "sample_flow", "dataset", "method", "procedure", "intervention", "measurement", "outcome", "result", "statistical_result", "table_result", "limitation", "conclusion", "implication", "future_work", "prior_work", "definition"]
Scope = Literal["current_study", "prior_work", "background", "unclear"]
Support = Literal["direct", "partial", "unsupported", "unclear"]


class NumericFact(StrictModel):
    raw: str
    normalized: str = ""
    role: str = ""
    unit: str | None = None
    comparator: str | None = None
    group: str | None = None
    timepoint: str | None = None
    uncertainty_type: str | None = None
    uncertainty_value: str | None = None
    p_relation: str | None = None
    p_value: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class TableCellRef(StrictModel):
    table_id: str
    row_label: str
    column_label: str
    value: str


class EvidenceRecord(StrictModel):
    evidence_id: str = ""
    type: EvidenceType
    claim: str = Field(min_length=3)
    source_scope: Scope
    source_refs: list[str] = Field(min_length=1)
    section: str = ""
    numeric_facts: list[NumericFact] = Field(default_factory=list)
    table_cells: list[TableCellRef] = Field(default_factory=list)
    support: Support = "unclear"
    importance: Literal["high", "medium", "low"] = "medium"


class EvidenceCandidate(StrictModel):
    type: EvidenceType
    claim: str = Field(min_length=3, max_length=600)
    source_scope: Scope
    source_refs: list[str] = Field(min_length=1)
    importance: Literal["high", "medium", "low"] = "medium"
    table_cells: list[TableCellRef] = Field(default_factory=list)


class CandidateBatch(StrictModel):
    evidence: list[EvidenceCandidate] = Field(default_factory=list)


class RoleCandidate(StrictModel):
    entity: str = Field(min_length=2, max_length=120)
    role: str = Field(min_length=15, max_length=300, description="What the entity does or estimates, not its category label")
    source_scope: Scope
    source_refs: list[str] = Field(min_length=1)


class RoleBatch(StrictModel):
    roles: list[RoleCandidate] = Field(default_factory=list)


class EvidenceStore(StrictModel):
    schema_version: Literal[1] = 1
    evidence: list[EvidenceRecord]


class SupportDecision(StrictModel):
    support: Support
    reason: str


class ScopeDecision(StrictModel):
    source_scope: Scope
    reason: str


class ResearchReportSentence(StrictModel):
    text: str = Field(min_length=3)
    evidence_ids: list[str] = Field(min_length=1)


class ResearchReportSection(StrictModel):
    title: str
    sentences: list[ResearchReportSentence] = Field(min_length=1)


class SectionDraft(StrictModel):
    sentences: list[ResearchReportSentence] = Field(min_length=1)


class SectionEvidencePacket(StrictModel):
    title: str
    mandatory: list[str] = Field(default_factory=list)
    supporting: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class ResearchReportPlan(StrictModel):
    schema_version: Literal[1] = 1
    packets: list[SectionEvidencePacket]


class ResearchReport(StrictModel):
    schema_version: Literal[1] = 1
    source_filename: str
    primary_kind: str
    sections: list[ResearchReportSection] = Field(min_length=1)


class ResearchCoverage(StrictModel):
    schema_version: Literal[1] = 1
    mandatory_evidence: int
    mandatory_covered: int
    mandatory_missing: list[str]
    citation_resolution: float
    unsupported_numeric_claims: int
    unsupported_sentences: int
    invalid_evidence_ids: int


class ResearchDiagnostics(StrictModel):
    schema_version: Literal[1] = 1
    current_stage: str = "PDF_VALIDATION"
    completed_stages: list[str] = Field(default_factory=list)
    failed_stage: str | None = None
    extraction: dict = Field(default_factory=dict)
    model_calls: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    report: dict = Field(default_factory=dict)
    failure: dict | None = None
