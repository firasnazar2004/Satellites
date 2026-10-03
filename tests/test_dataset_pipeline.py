"""Tests for deterministic CSV inspection and cleaning."""

import json
import tempfile
import unittest
from pathlib import Path

import polars as pl

from app.pipelines.dataset import (
    INSPECTION_FILE_NAME,
    inspect_csv,
)
from app.pipelines.dataset_full import clean_dataset as process_dataset_file


class DatasetPipelineTests(unittest.TestCase):
    def test_inspection_detects_delimiter_and_wrong_width_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "malformed.csv"
            input_path.write_text(
                "name;age;city\nAlice;30;Riyadh\nBob;41\n",
                encoding="utf-8",
            )

            inspection = inspect_csv(input_path)

            self.assertEqual(inspection.delimiter, ";")
            self.assertEqual(inspection.data_row_count, 2)
            self.assertEqual(inspection.malformed_row_count, 1)
            self.assertEqual(inspection.malformed_rows[0].line_number, 3)

    def test_pipeline_writes_typed_parquet_and_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "study.csv"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text(
                " Name , Age , Joined , Score , Active , Subject ID \n"
                " Alice ,30,31/12/2024,10.5,yes,001\n"
                " Bob ,N/A,01/02/2025,9.0,no,002\n"
                " Bob ,N/A,01/02/2025,9.0,no,002\n",
                encoding="utf-8",
            )

            artifacts = process_dataset_file(
                input_path,
                output_dir,
                trust_date_order=True,
            )

            frame = pl.read_parquet(output_dir / "cleaned.parquet")
            report = json.loads(
                (output_dir / "dataset_report.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                frame.columns,
                ["Name", "Age", "Joined", "Score", "Active", "Subject ID"],
            )
            self.assertEqual(frame.schema["Age"], pl.Int64)
            self.assertEqual(frame.schema["Joined"], pl.Date)
            self.assertEqual(frame.schema["Score"], pl.Float64)
            self.assertEqual(frame.schema["Active"], pl.Boolean)
            self.assertEqual(frame.schema["Subject ID"], pl.String)
            self.assertEqual(frame["Name"].to_list(), ["Alice", "Bob"])
            self.assertEqual(frame["Age"].null_count(), 1)
            self.assertEqual(report["duplicate_row_count"], 0)
            self.assertEqual(report["headers"][" Name "], "Name")
            self.assertEqual(len(artifacts), 7)
            repair_log = json.loads(
                (output_dir / "repair_log.json").read_text(encoding="utf-8")
            )
            self.assertEqual(repair_log["ambiguous_rows"], 1)

    def test_malformed_csv_is_quarantined_without_stopping_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "malformed.csv"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text(
                "name,age\nAlice,30\nBob,41,unexpected\n",
                encoding="utf-8",
            )

            process_dataset_file(input_path, output_dir)

            inspection = json.loads(
                (output_dir / INSPECTION_FILE_NAME).read_text(encoding="utf-8")
            )
            repair_log = json.loads(
                (output_dir / "repair_log.json").read_text(encoding="utf-8")
            )
            frame = pl.read_parquet(output_dir / "cleaned.parquet")
            self.assertEqual(inspection["malformed_row_count"], 0)
            self.assertEqual(repair_log["ambiguous_rows"], 1)
            self.assertEqual(frame.height, 1)

    def test_unique_schema_valid_shift_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "shifted.csv"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text(
                "name,age,score\n"
                "Alice Smith,30,90\n"
                "Bob Jones,31,91\n"
                "Smith, Carol,32,92\n",
                encoding="utf-8",
            )

            process_dataset_file(input_path, output_dir)

            frame = pl.read_parquet(output_dir / "cleaned.parquet")
            repair_log = json.loads(
                (output_dir / "repair_log.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                frame["name"].to_list(),
                ["Alice Smith", "Bob Jones", "Smith, Carol"],
            )
            self.assertEqual(repair_log["repaired_rows"], 1)
            self.assertEqual(repair_log["ambiguous_rows"], 0)

    def test_ambiguous_day_month_date_is_quarantined_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "dates.csv"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text(
                "record_id,visit_date\n1,31/12/2025\n2,03/04/2026\n",
                encoding="utf-8",
            )

            process_dataset_file(input_path, output_dir)

            frame = pl.read_parquet(output_dir / "cleaned.parquet")
            repair_log = json.loads(
                (output_dir / "repair_log.json").read_text(encoding="utf-8")
            )
            self.assertEqual(frame.height, 1)
            self.assertEqual(repair_log["ambiguous_rows"], 1)
            self.assertIn(
                "ambiguous day/month date",
                repair_log["records"][0]["reasons"][0],
            )

            trusted_output_dir = root / "trusted-output"
            trusted_output_dir.mkdir()
            process_dataset_file(
                input_path,
                trusted_output_dir,
                trust_date_order=True,
            )
            trusted_frame = pl.read_parquet(trusted_output_dir / "cleaned.parquet")
            self.assertEqual(trusted_frame.height, 2)

    def test_malformed_boundary_quote_is_repaired_when_value_is_unambiguous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "quotes.csv"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text(
                'record_id,note\n1,Routine follow-up\n2,"Routine follow-up\n',
                encoding="utf-8",
            )

            process_dataset_file(input_path, output_dir)

            frame = pl.read_parquet(output_dir / "cleaned.parquet")
            repair_log = json.loads(
                (output_dir / "repair_log.json").read_text(encoding="utf-8")
            )
            self.assertEqual(frame.height, 2)
            self.assertEqual(repair_log["repaired_rows"], 1)


if __name__ == "__main__":
    unittest.main()
