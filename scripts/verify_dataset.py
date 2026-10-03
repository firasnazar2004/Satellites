"""Fixture comparison and a serial 100k-row acceptance run; never learns from oracle."""

import csv
import json
import sys
from pathlib import Path
from uuid import uuid4

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.execution import execute


def main():
    root = Path("outputs/dataset-verification") / str(uuid4())
    root.mkdir(parents=True)
    fixtures = Path("tests/fixtures")
    results = {}
    if (fixtures / "faulty_dataset.csv").is_file():
        out = root / "fixture"
        out.mkdir()
        execute("dataset", fixtures / "faulty_dataset.csv", out, {"interpret": False})
        with (fixtures / "expected_clean_dataset.csv").open(newline="") as f:
            expected = list(csv.DictReader(f))
        with (out / "row_status.csv").open(newline="") as f:
            status = list(csv.DictReader(f))
        with (out / "repaired.csv").open(newline="") as f:
            actual = list(csv.DictReader(f))
        accepted = [
            expected[int(s["source_line"]) - 2]
            for s in status
            if s["status"] != "AMBIGUOUS"
        ]
        assert actual == accepted, "Accepted rows differ from expected fixture"
        log = json.loads((out / "repair_log.json").read_text())
        results["fixture"] = {
            k: log[k]
            for k in ("total_rows", "valid_rows", "repaired_rows", "ambiguous_rows")
        }
        results["fixture"]["accepted_cell_mismatches"] = 0
        print("Fixture comparison passed", results["fixture"], flush=True)
    source = root / "large.csv"
    with source.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "value", "visit_date"])
        for i in range(100_000):
            writer.writerow([i + 1, i % 100, "2026-04-03"])
    out = root / "large"
    out.mkdir()
    execute("dataset", source, out, {"interpret": False})
    with duckdb.connect(str(out / "dataset.duckdb"), read_only=True) as db:
        count, mean = db.execute("SELECT count(*),avg(value) FROM cleaned").fetchone()
    assert count == 100_000 and mean == 49.5
    statistics = json.loads((out / "statistics.json").read_text())
    assert statistics["results"][0]["summary"]["value"]["mean"] == 49.5
    results["large"] = {
        "rows": count,
        "R_mean": 49.5,
        **json.loads((out / "runtime.json").read_text()),
    }
    (root / "results.json").write_text(json.dumps(results, indent=2))
    print("DATASET VERIFICATION PASSED", root, results["large"], flush=True)


if __name__ == "__main__":
    main()
