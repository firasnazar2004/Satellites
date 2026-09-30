"""Structured metadata produced by CSV ingestion and cleaning."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DateOrder = Literal["dmy", "mdy", "ymd"]


class MalformedRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int
    expected_columns: int
    actual_columns: int


class CsvInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file: Path
    encoding: str
    delimiter: str
    original_headers: list[str]
    normalized_headers: list[str]
    data_row_count: int
    blank_row_count: int
    malformed_row_count: int
    malformed_rows: list[MalformedRow] = Field(default_factory=list)


class ColumnProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    data_type: str
    missing_count: int
    non_null_count: int
    unique_count: int
    date_format: str | None = None


class DatasetReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file: Path
    encoding: str
    delimiter: str
    date_order: DateOrder
    row_count: int
    column_count: int
    duplicate_row_count: int
    headers: dict[str, str]
    columns: list[ColumnProfile]
