"""Tests for deterministic CSV inspection and cleaning."""

import json
import tempfile
import unittest
from pathlib import Path

import polars as pl

from app.pipelines.dataset import (
    INSPECTION_FILE_NAME,
    MalformedCsvError,
    inspect_csv,
    process_dataset_file,
)


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

            artifacts = process_dataset_file(input_path, output_dir)

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
            self.assertEqual(frame["Name"].to_list(), ["Alice", "Bob", "Bob"])
            self.assertEqual(frame["Age"].null_count(), 2)
            self.assertEqual(report["duplicate_row_count"], 1)
            self.assertEqual(report["headers"][" Name "], "Name")
            self.assertEqual(len(artifacts), 3)

    def test_malformed_csv_is_recorded_then_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "malformed.csv"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text(
                "name,age\nAlice,30\nBob,41,unexpected\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(MalformedCsvError, "MVP Step 5"):
                process_dataset_file(input_path, output_dir)

            inspection = json.loads(
                (output_dir / INSPECTION_FILE_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(inspection["malformed_row_count"], 1)


if __name__ == "__main__":
    unittest.main()
