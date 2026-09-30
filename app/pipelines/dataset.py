"""Deterministic CSV ingestion and basic cleaning."""

import csv
import io
from pathlib import Path

import polars as pl

from app.models.dataset import (
    ColumnProfile,
    CsvInspection,
    DatasetReport,
    DateOrder,
    MalformedRow,
)


INSPECTION_FILE_NAME = "csv_inspection.json"
REPORT_FILE_NAME = "dataset_report.json"
PARQUET_FILE_NAME = "cleaned.parquet"
MISSING_MARKERS = frozenset({"", "na", "n/a", "null", "none", "missing"})
MAX_REPORTED_MALFORMED_ROWS = 100


class MalformedCsvError(ValueError):
    """Raised when row widths must be repaired before safe ingestion."""


def inspect_csv(input_path: Path) -> CsvInspection:
    """Inspect encoding, delimiter, headers, and record widths without loading data."""

    encoding, sample = _read_sample(input_path)
    delimiter = _detect_delimiter(sample)

    original_headers: list[str] = []
    normalized_headers: list[str] = []
    malformed_rows: list[MalformedRow] = []
    malformed_row_count = 0
    data_row_count = 0
    blank_row_count = 0

    try:
        with input_path.open("r", encoding=encoding, newline="") as input_file:
            reader = csv.reader(input_file, delimiter=delimiter, strict=True)
            try:
                original_headers = next(reader)
            except StopIteration as exc:
                raise ValueError(f"CSV file is empty: {input_path}") from exc

            normalized_headers = _normalize_headers(original_headers)
            expected_columns = len(original_headers)

            for row in reader:
                if not row or all(not value.strip() for value in row):
                    blank_row_count += 1
                    continue

                data_row_count += 1
                if len(row) != expected_columns:
                    malformed_row_count += 1
                    if len(malformed_rows) < MAX_REPORTED_MALFORMED_ROWS:
                        malformed_rows.append(
                            MalformedRow(
                                line_number=reader.line_num,
                                expected_columns=expected_columns,
                                actual_columns=len(row),
                            )
                        )
    except csv.Error as exc:
        raise MalformedCsvError(
            f"CSV syntax error near physical line {reader.line_num}: {exc}"
        ) from exc

    return CsvInspection(
        source_file=input_path.resolve(),
        encoding=encoding,
        delimiter=delimiter,
        original_headers=original_headers,
        normalized_headers=normalized_headers,
        data_row_count=data_row_count,
        blank_row_count=blank_row_count,
        malformed_row_count=malformed_row_count,
        malformed_rows=malformed_rows,
    )


def process_dataset_file(
    input_path: Path,
    output_dir: Path,
    *,
    date_order: DateOrder = "dmy",
) -> list[Path]:
    """Validate and clean a well-formed CSV into typed Parquet plus reports."""

    inspection = inspect_csv(input_path)
    inspection_path = output_dir / INSPECTION_FILE_NAME
    inspection_path.write_text(inspection.model_dump_json(indent=2), encoding="utf-8")

    if inspection.malformed_row_count:
        raise MalformedCsvError(
            f"Found {inspection.malformed_row_count} row(s) with the wrong number "
            f"of columns. See {inspection_path}. Automated repair belongs to MVP Step 5."
        )

    frame = pl.read_csv(
        input_path,
        separator=inspection.delimiter,
        encoding="utf8",
        has_header=True,
        new_columns=inspection.normalized_headers,
        infer_schema=False,
    )
    frame = _normalize_string_values(frame)
    frame, date_formats = _infer_and_cast_types(frame, date_order=date_order)

    duplicate_row_count = frame.height - frame.unique().height
    columns = [
        ColumnProfile(
            name=name,
            data_type=str(frame.schema[name]),
            missing_count=frame.get_column(name).null_count(),
            non_null_count=frame.get_column(name).len()
            - frame.get_column(name).null_count(),
            unique_count=frame.get_column(name).drop_nulls().n_unique(),
            date_format=date_formats.get(name),
        )
        for name in frame.columns
    ]

    parquet_path = output_dir / PARQUET_FILE_NAME
    frame.write_parquet(parquet_path, compression="zstd")

    report = DatasetReport(
        source_file=input_path.resolve(),
        encoding=inspection.encoding,
        delimiter=inspection.delimiter,
        date_order=date_order,
        row_count=frame.height,
        column_count=frame.width,
        duplicate_row_count=duplicate_row_count,
        headers=dict(
            zip(
                inspection.original_headers,
                inspection.normalized_headers,
                strict=True,
            )
        ),
        columns=columns,
    )
    report_path = output_dir / REPORT_FILE_NAME
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return [parquet_path, report_path, inspection_path]


def _read_sample(input_path: Path, sample_size: int = 65_536) -> tuple[str, str]:
    with input_path.open("rb") as input_file:
        raw_sample = input_file.read(sample_size)
    if not raw_sample:
        raise ValueError(f"CSV file is empty: {input_path}")

    encoding = "utf-8-sig" if raw_sample.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        return encoding, raw_sample.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(
            "CSV must use UTF-8 or UTF-8 with BOM for MVP Step 4"
        ) from exc


def _detect_delimiter(sample: str) -> str:
    candidates = ",;\t|"
    scores: list[tuple[int, int, str]] = []

    for delimiter in candidates:
        try:
            rows = list(csv.reader(io.StringIO(sample), delimiter=delimiter))
        except csv.Error:
            continue
        rows = [row for row in rows if row and any(value.strip() for value in row)]
        if not rows or len(rows[0]) < 2:
            continue

        header_width = len(rows[0])
        matching_width_rows = sum(len(row) == header_width for row in rows[1:])
        scores.append((matching_width_rows, header_width, delimiter))

    if scores:
        return max(scores)[2]
    if not any(delimiter in sample for delimiter in candidates):
        return ","
    raise ValueError("Could not determine a CSV delimiter from the header row")


def _normalize_headers(headers: list[str]) -> list[str]:
    if not headers:
        raise ValueError("CSV header row has no columns")

    normalized = [header.strip() for header in headers]
    empty_positions = [index + 1 for index, name in enumerate(normalized) if not name]
    if empty_positions:
        raise ValueError(f"CSV contains empty header names at columns {empty_positions}")

    duplicates = sorted({name for name in normalized if normalized.count(name) > 1})
    if duplicates:
        raise ValueError(
            f"CSV contains duplicate header names after trimming: {duplicates}"
        )
    return normalized


def _normalize_string_values(frame: pl.DataFrame) -> pl.DataFrame:
    expressions = []
    for name in frame.columns:
        stripped = pl.col(name).str.strip_chars()
        expressions.append(
            pl.when(stripped.str.to_lowercase().is_in(MISSING_MARKERS))
            .then(pl.lit(None, dtype=pl.String))
            .otherwise(stripped)
            .alias(name)
        )
    return frame.with_columns(expressions)


def _infer_and_cast_types(
    frame: pl.DataFrame,
    *,
    date_order: DateOrder,
) -> tuple[pl.DataFrame, dict[str, str]]:
    expressions = []
    date_formats: dict[str, str] = {}

    for name in frame.columns:
        series = frame.get_column(name).drop_nulls()
        expression = pl.col(name)

        if series.is_empty():
            expressions.append(expression)
            continue

        date_format = _matching_date_format(series, date_order=date_order)
        if date_format:
            expressions.append(
                expression.str.strptime(pl.Date, format=date_format, strict=True).alias(name)
            )
            date_formats[name] = date_format
        elif _is_boolean_series(series):
            lowered = expression.str.to_lowercase()
            expressions.append(
                pl.when(lowered.is_in(["true", "yes"]))
                .then(True)
                .when(lowered.is_in(["false", "no"]))
                .then(False)
                .otherwise(None)
                .cast(pl.Boolean)
                .alias(name)
            )
        elif _has_leading_zero_integer(series):
            expressions.append(expression)
        elif _all_castable(series, pl.Int64):
            expressions.append(expression.cast(pl.Int64).alias(name))
        elif _all_castable(series, pl.Float64):
            expressions.append(expression.cast(pl.Float64).alias(name))
        else:
            expressions.append(expression)

    return frame.with_columns(expressions), date_formats


def _matching_date_format(series: pl.Series, *, date_order: DateOrder) -> str | None:
    if not series.str.contains(r"^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}$").all():
        return None

    preferred_formats = {
        "dmy": ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"],
        "mdy": ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y"],
        "ymd": ["%Y-%m-%d", "%Y/%m/%d"],
    }
    for date_format in preferred_formats[date_order]:
        parsed = series.str.strptime(pl.Date, format=date_format, strict=False)
        if parsed.null_count() == 0:
            return date_format
    return None


def _is_boolean_series(series: pl.Series) -> bool:
    return series.str.to_lowercase().is_in(["true", "false", "yes", "no"]).all()


def _has_leading_zero_integer(series: pl.Series) -> bool:
    return series.str.contains(r"^[+-]?0\d+$").any()


def _all_castable(series: pl.Series, data_type: pl.DataType) -> bool:
    return series.cast(data_type, strict=False).null_count() == 0
