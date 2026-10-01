"""Conservative, deterministic repair for malformed single-record-per-line CSVs."""

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path

from app.models.dataset import DateOrder, RepairSummary, RowRepairRecord, RowStatus


REPAIRED_FILE_NAME = "repaired.csv"
QUARANTINE_FILE_NAME = "quarantine.csv"
REPAIR_LOG_FILE_NAME = "repair_log.json"
ROW_STATUS_FILE_NAME = "row_status.csv"
MISSING_MARKERS = frozenset({"", "na", "n/a", "null", "none", "missing", "-"})


@dataclass(frozen=True)
class RepairResult:
    repaired_path: Path
    quarantine_path: Path
    repair_log_path: Path
    row_status_path: Path
    original_headers: list[str]
    normalized_headers: list[str]

    @property
    def artifacts(self) -> list[Path]:
        return [
            self.repaired_path,
            self.quarantine_path,
            self.repair_log_path,
            self.row_status_path,
        ]


@dataclass
class ColumnRule:
    name: str
    kind: str
    required: bool
    categorical: bool = False
    canonical_values: dict[str, str] | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None


def repair_csv_file(
    input_path: Path,
    output_dir: Path,
    *,
    date_order: DateOrder,
    trust_date_order: bool = False,
) -> RepairResult:
    """Classify every physical row and write only safe rows to repaired CSV."""

    encoding, sample = _read_sample(input_path)
    delimiter = _detect_delimiter(sample)
    original_headers, header, raw_rows = _read_physical_rows(
        input_path,
        encoding,
        delimiter,
    )
    rules = _infer_rules(header, raw_rows, delimiter, date_order=date_order)
    primary_key_index = _primary_key_index(header, raw_rows, delimiter)

    repaired_path = output_dir / REPAIRED_FILE_NAME
    quarantine_path = output_dir / QUARANTINE_FILE_NAME
    repair_log_path = output_dir / REPAIR_LOG_FILE_NAME
    row_status_path = output_dir / ROW_STATUS_FILE_NAME

    counts = Counter({status.value: 0 for status in RowStatus})
    records: list[RowRepairRecord] = []
    seen_rows: set[tuple[str, ...]] = set()
    seen_keys: set[str] = set()
    seen_source_rows: set[tuple[str, ...]] = set()
    seen_source_keys: set[str] = set()

    with (
        repaired_path.open("w", encoding="utf-8", newline="") as repaired_file,
        quarantine_path.open("w", encoding="utf-8", newline="") as quarantine_file,
        row_status_path.open("w", encoding="utf-8", newline="") as status_file,
    ):
        repaired_writer = csv.writer(repaired_file, lineterminator="\n")
        quarantine_writer = csv.writer(quarantine_file, lineterminator="\n")
        status_writer = csv.writer(status_file, lineterminator="\n")
        repaired_writer.writerow(header)
        quarantine_writer.writerow(["source_line", "record_key", "reason", "raw_row"])
        status_writer.writerow(["source_line", "record_key", "status", "reason"])

        for line_number, raw_line in raw_rows:
            fields = _parse_physical_line(raw_line, delimiter)
            record_key = fields[primary_key_index].strip() if (
                primary_key_index is not None and len(fields) > primary_key_index
            ) else None
            outcome = _repair_row(
                fields,
                raw_line=raw_line,
                rules=rules,
                delimiter=delimiter,
                date_order=date_order,
                trust_date_order=trust_date_order,
            )

            status = outcome.status
            reasons = list(outcome.reasons)
            repaired_fields = outcome.fields

            source_fingerprint = tuple(value.strip() for value in fields)
            source_is_duplicate = source_fingerprint in seen_source_rows
            source_key_is_duplicate = (
                record_key is not None and record_key in seen_source_keys
            )
            seen_source_rows.add(source_fingerprint)
            if record_key is not None:
                seen_source_keys.add(record_key)

            if source_is_duplicate:
                status = RowStatus.AMBIGUOUS
                reasons = ["exact duplicate of an earlier source row"]
                repaired_fields = None
            elif source_key_is_duplicate:
                status = RowStatus.AMBIGUOUS
                reasons = ["duplicate primary-key value in source"]
                repaired_fields = None

            if repaired_fields is not None:
                row_key = tuple(repaired_fields)
                repaired_record_key = (
                    repaired_fields[primary_key_index]
                    if primary_key_index is not None
                    else None
                )
                if row_key in seen_rows:
                    status = RowStatus.AMBIGUOUS
                    reasons = ["exact duplicate of an earlier accepted row"]
                    repaired_fields = None
                elif repaired_record_key is not None and repaired_record_key in seen_keys:
                    status = RowStatus.AMBIGUOUS
                    reasons = ["duplicate primary-key value"]
                    repaired_fields = None

            reason_text = "; ".join(reasons)
            counts[status.value] += 1
            status_writer.writerow([line_number, record_key or "", status.value, reason_text])

            if repaired_fields is None:
                quarantine_writer.writerow(
                    [line_number, record_key or "", reason_text, raw_line]
                )
            else:
                repaired_writer.writerow(repaired_fields)
                seen_rows.add(tuple(repaired_fields))
                if primary_key_index is not None:
                    seen_keys.add(repaired_fields[primary_key_index])

            if status is not RowStatus.VALID:
                records.append(
                    RowRepairRecord(
                        source_line=line_number,
                        record_key=record_key,
                        status=status,
                        reasons=reasons,
                        original_fields=fields,
                        repaired_fields=repaired_fields,
                    )
                )

    summary = RepairSummary(
        source_file=input_path.resolve(),
        repaired_file=repaired_path.resolve(),
        quarantine_file=quarantine_path.resolve(),
        total_rows=len(raw_rows),
        valid_rows=counts[RowStatus.VALID.value],
        repaired_rows=counts[RowStatus.REPAIRED.value],
        ambiguous_rows=counts[RowStatus.AMBIGUOUS.value],
        original_headers=original_headers,
        normalized_headers=header,
        column_kinds={rule.name: rule.kind for rule in rules},
        primary_key=(header[primary_key_index] if primary_key_index is not None else None),
        records=records,
    )
    repair_log_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return RepairResult(
        repaired_path=repaired_path,
        quarantine_path=quarantine_path,
        repair_log_path=repair_log_path,
        row_status_path=row_status_path,
        original_headers=original_headers,
        normalized_headers=header,
    )


@dataclass(frozen=True)
class RowOutcome:
    status: RowStatus
    reasons: tuple[str, ...]
    fields: list[str] | None


def _repair_row(
    fields: list[str],
    *,
    raw_line: str,
    rules: list[ColumnRule],
    delimiter: str,
    date_order: DateOrder,
    trust_date_order: bool,
) -> RowOutcome:
    expected_width = len(rules)
    candidates = _width_candidates(fields, expected_width, delimiter)
    valid_candidates: dict[tuple[str, ...], tuple[str, ...]] = {}
    validation_errors: set[str] = set()

    for candidate, width_action in candidates:
        normalized, actions, errors = _normalize_candidate(
            candidate,
            rules,
            date_order=date_order,
            trust_date_order=trust_date_order,
        )
        if errors:
            validation_errors.update(errors)
            continue
        all_actions = list(actions)
        if width_action:
            all_actions.insert(0, width_action)
        if _has_quote_anomaly(raw_line, delimiter):
            all_actions.append("normalized malformed quoting")
        valid_candidates[tuple(normalized)] = tuple(dict.fromkeys(all_actions))

    if not valid_candidates:
        if len(fields) != expected_width:
            reasons = [
                f"no unique schema-valid alignment for {len(fields)} fields; "
                f"expected {expected_width}"
            ]
        else:
            reasons = sorted(validation_errors) or ["row failed schema validation"]
        return RowOutcome(RowStatus.AMBIGUOUS, tuple(reasons), None)

    if len(valid_candidates) > 1:
        return RowOutcome(
            RowStatus.AMBIGUOUS,
            (f"multiple schema-valid repairs ({len(valid_candidates)})",),
            None,
        )

    normalized_tuple, actions = next(iter(valid_candidates.items()))
    normalized = list(normalized_tuple)
    status = RowStatus.REPAIRED if actions or normalized != fields else RowStatus.VALID
    reasons = actions or ("row already conforms to inferred schema",)
    return RowOutcome(status, reasons, normalized)


def _normalize_candidate(
    fields: list[str],
    rules: list[ColumnRule],
    *,
    date_order: DateOrder,
    trust_date_order: bool,
) -> tuple[list[str], list[str], list[str]]:
    normalized: list[str] = []
    actions: list[str] = []
    errors: list[str] = []

    for value, rule in zip(fields, rules, strict=True):
        stripped = value.strip()
        if stripped != value:
            actions.append(f"trimmed whitespace in {rule.name}")

        if stripped.casefold() in MISSING_MARKERS:
            if rule.required:
                errors.append(f"missing required value in {rule.name}")
            normalized.append("")
            continue

        if rule.kind == "date":
            if not trust_date_order and _is_ambiguous_day_month(stripped):
                errors.append(f"ambiguous day/month date in {rule.name}")
                normalized.append(stripped)
                continue
            parsed = _parse_date(stripped, date_order=date_order)
            if parsed is None:
                errors.append(f"invalid date in {rule.name}")
                normalized.append(stripped)
            else:
                canonical = parsed.strftime("%d/%m/%Y")
                if canonical != stripped:
                    actions.append(f"normalized date in {rule.name}")
                normalized.append(canonical)
        elif rule.kind in {"integer", "float"}:
            number = _parse_number(stripped, integer=rule.kind == "integer")
            if number is None:
                errors.append(f"invalid {rule.kind} in {rule.name}")
            elif (
                rule.lower_bound is not None
                and number < rule.lower_bound
                or rule.upper_bound is not None
                and number > rule.upper_bound
            ):
                errors.append(f"numeric outlier in {rule.name}")
            normalized.append(stripped)
        elif rule.kind == "boolean":
            lowered = stripped.casefold()
            if lowered not in {"true", "false", "yes", "no"}:
                errors.append(f"invalid boolean in {rule.name}")
            normalized.append(lowered)
        else:
            canonical_values = rule.canonical_values or {}
            lookup = stripped.casefold()
            if rule.categorical and lookup not in canonical_values:
                without_stray_quotes = stripped.strip('"').casefold()
                if without_stray_quotes in canonical_values:
                    lookup = without_stray_quotes
                    actions.append(f"removed stray quote in {rule.name}")
                else:
                    errors.append(f"unknown categorical value in {rule.name}")
                    normalized.append(stripped)
                    continue
            canonical = canonical_values.get(lookup, stripped)
            if canonical != stripped:
                actions.append(f"canonicalized text in {rule.name}")
            normalized.append(canonical)

    return normalized, actions, errors


def _width_candidates(
    fields: list[str],
    expected_width: int,
    delimiter: str,
) -> list[tuple[list[str], str | None]]:
    if len(fields) == expected_width:
        return [(fields, None)]
    if len(fields) < expected_width:
        missing = expected_width - len(fields)
        if missing > 2:
            return []
        results = []
        for positions in combinations(range(expected_width), missing):
            source = iter(fields)
            inserted = set(positions)
            candidate = ["" if index in inserted else next(source) for index in range(expected_width)]
            results.append((candidate, f"inserted {missing} missing field(s)"))
        return results

    extra = len(fields) - expected_width
    if extra > 2:
        return []

    results = []
    for boundaries in combinations(range(1, len(fields)), expected_width - 1):
        starts = (0, *boundaries)
        ends = (*boundaries, len(fields))
        candidate = [
            f"{delimiter} ".join(part.strip() for part in fields[start:end])
            for start, end in zip(starts, ends, strict=True)
        ]
        results.append((candidate, f"merged {extra} shifted field(s)"))
    return results


def _infer_rules(
    header: list[str],
    raw_rows: list[tuple[int, str]],
    delimiter: str,
    *,
    date_order: DateOrder,
) -> list[ColumnRule]:
    width = len(header)
    parsed_rows = []
    for _, raw_line in raw_rows:
        fields = _parse_physical_line(raw_line, delimiter)
        if len(fields) == width and not _has_quote_anomaly(raw_line, delimiter):
            parsed_rows.append([value.strip() for value in fields])

    if not parsed_rows:
        raise ValueError("Cannot infer a schema because no rows match the header width")

    rules = []
    for index, name in enumerate(header):
        values = [row[index] for row in parsed_rows]
        nonmissing = [value for value in values if value.casefold() not in MISSING_MARKERS]
        required = bool(values) and len(nonmissing) / len(values) >= 0.98
        kind = _infer_kind(nonmissing, date_order=date_order)
        rule = ColumnRule(name=name, kind=kind, required=required)

        if kind == "string":
            grouped: dict[str, Counter[str]] = {}
            for value in nonmissing:
                grouped.setdefault(value.casefold(), Counter())[value] += 1
            repeated_groups = {
                key: variants
                for key, variants in grouped.items()
                if sum(variants.values()) >= 2
            }
            unique_ratio = len(grouped) / max(len(nonmissing), 1)
            rule.categorical = bool(repeated_groups) and unique_ratio <= 0.2
            if rule.categorical:
                rule.canonical_values = {
                    key: variants.most_common(1)[0][0]
                    for key, variants in repeated_groups.items()
                }
        elif kind in {"integer", "float"}:
            numeric_values = sorted(
                number
                for value in nonmissing
                if (number := _parse_number(value, integer=kind == "integer"))
                is not None
            )
            if len(numeric_values) >= 20:
                q1 = _quantile(numeric_values, 0.25)
                q3 = _quantile(numeric_values, 0.75)
                spread = q3 - q1
                if spread > 0:
                    rule.lower_bound = q1 - spread
                    rule.upper_bound = q3 + spread
        rules.append(rule)
    return rules


def _infer_kind(values: list[str], *, date_order: DateOrder) -> str:
    if not values:
        return "string"

    total = len(values)
    date_rate = sum(_parse_date(value, date_order=date_order) is not None for value in values) / total
    integer_rate = sum(_parse_number(value, integer=True) is not None for value in values) / total
    float_rate = sum(_parse_number(value, integer=False) is not None for value in values) / total
    boolean_rate = sum(value.casefold() in {"true", "false", "yes", "no"} for value in values) / total

    if date_rate >= 0.9:
        return "date"
    if boolean_rate >= 0.9:
        return "boolean"
    if integer_rate >= 0.9:
        return "integer"
    if float_rate >= 0.9:
        return "float"
    return "string"


def _primary_key_index(
    header: list[str],
    raw_rows: list[tuple[int, str]],
    delimiter: str,
) -> int | None:
    for index, name in enumerate(header):
        normalized = re.sub(r"\W+", "_", name.casefold()).strip("_")
        if normalized == "id" or normalized.endswith("_id"):
            return index
    return None


def _read_sample(input_path: Path, sample_size: int = 65_536) -> tuple[str, str]:
    with input_path.open("rb") as input_file:
        raw_sample = input_file.read(sample_size)
    if not raw_sample:
        raise ValueError(f"CSV file is empty: {input_path}")
    encoding = "utf-8-sig" if raw_sample.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        return encoding, raw_sample.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError("CSV repair currently requires UTF-8 input") from exc


def _detect_delimiter(sample: str) -> str:
    header_line = sample.splitlines()[0]
    candidates = ",;\t|"
    scored = []
    for delimiter in candidates:
        fields = next(csv.reader([header_line], delimiter=delimiter, strict=False))
        if len(fields) > 1:
            scored.append((len(fields), delimiter))
    if scored:
        return max(scored)[1]
    return ","


def _read_physical_rows(
    input_path: Path,
    encoding: str,
    delimiter: str,
) -> tuple[list[str], list[str], list[tuple[int, str]]]:
    with input_path.open("r", encoding=encoding, newline="") as input_file:
        lines = [
            (line_number, line.rstrip("\r\n"))
            for line_number, line in enumerate(input_file, 1)
        ]
    if not lines:
        raise ValueError(f"CSV file is empty: {input_path}")
    original_headers = _parse_physical_line(lines[0][1], delimiter)
    header = [value.strip() for value in original_headers]
    if not header or any(not name for name in header):
        raise ValueError("CSV requires a non-empty header row")
    if len(set(header)) != len(header):
        raise ValueError("CSV header names must be unique after trimming")
    raw_rows = [(line_number, line) for line_number, line in lines[1:] if line.strip()]
    return original_headers, header, raw_rows


def _parse_physical_line(raw_line: str, delimiter: str) -> list[str]:
    return next(csv.reader([raw_line], delimiter=delimiter, strict=False))


def _has_quote_anomaly(raw_line: str, delimiter: str) -> bool:
    if '"' not in raw_line:
        return False
    try:
        next(csv.reader(io.StringIO(raw_line + "\n"), delimiter=delimiter, strict=True))
    except csv.Error:
        return True

    in_quotes = False
    field_start = True
    index = 0
    while index < len(raw_line):
        character = raw_line[index]
        if character == delimiter and not in_quotes:
            field_start = True
        elif character == '"':
            if in_quotes and index + 1 < len(raw_line) and raw_line[index + 1] == '"':
                index += 1
            elif field_start or in_quotes:
                in_quotes = not in_quotes
            else:
                return True
            field_start = False
        else:
            field_start = False
        index += 1
    return in_quotes


def _parse_date(value: str, *, date_order: DateOrder) -> datetime | None:
    formats = {
        "dmy": ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"],
        "mdy": ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d", "%d/%m/%Y"],
        "ymd": ["%Y-%m-%d", "%Y/%m/%d"],
    }
    for date_format in formats[date_order]:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return None


def _is_ambiguous_day_month(value: str) -> bool:
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match is None:
        return False
    first, second = int(match.group(1)), int(match.group(2))
    return first <= 12 and second <= 12 and first != second


def _parse_number(value: str, *, integer: bool) -> float | None:
    pattern = r"^[+-]?\d+$" if integer else r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$"
    if not re.fullmatch(pattern, value):
        return None
    return float(value)


def _quantile(values: list[float], fraction: float) -> float:
    return values[round((len(values) - 1) * fraction)]
