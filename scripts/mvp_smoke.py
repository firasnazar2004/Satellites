"""Real HTTP + local Qwen acceptance test. Run with a running Uvicorn server."""

import argparse
import csv
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
from openpyxl import load_workbook
from reportlab.pdfgen import canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    root = Path("outputs/verification") / str(uuid4())
    root.mkdir(parents=True)
    text = "Chlorophyll absorbs light. Photosynthesis converts light energy into chemical energy. The Calvin cycle uses carbon dioxide."
    notes = root / "notes.txt"
    notes.write_text(text)
    csv_path = root / "study.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["record_id", "age", "score", "visit_date"])
        for i in range(12):
            writer.writerow([i + 1, 20 + i, 40 + 2 * i + i % 3, "2026-04-03"])
    paper = root / "synthetic_study.pdf"
    pdf = canvas.Canvas(str(paper))
    pdf.setTitle("Synthetic validation study - not a real publication")
    page_texts = [
        [
            "Synthetic validation study - not a real publication",
            "Abstract",
            "Our objective was to investigate blood pressure after treatment.",
            "Methods",
            "We conducted a randomized controlled trial of treatment.",
            "The trial enrolled 120 adults.",
            "Results",
            "The mean difference was -8.4 mmHg.",
            "The 95% confidence interval was -11.1 to -5.7 mmHg.",
            "The p-value was 0.001.",
        ],
        [
            "Limitations",
            "Our study was limited to a single centre.",
            "Follow-up lasted 12 weeks.",
            "Conclusions",
            "Our trial found a difference in blood pressure after treatment.",
        ],
    ]
    for lines in page_texts:
        y = 760
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 26
        pdf.showPage()
    pdf.save()
    headers = (
        {"X-API-Key": os.environ["LOCAL_AI_API_KEY"]}
        if os.environ.get("LOCAL_AI_API_KEY")
        else {}
    )
    with httpx.Client(
        base_url=args.base_url, timeout=30, headers=headers, trust_env=False
    ) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/static/swagger/swagger-ui-bundle.js").status_code == 200
        health = client.get("/health").json()
        assert health["qwen3_8b_available"] and health["Rscript"], health
        requests = [
            ("flashcards", notes, {"cards_per_chunk": "3"}),
            (
                "dataset",
                csv_path,
                {
                    "analysis_plan": json.dumps(
                        {
                            "analyses": [
                                {"test": "descriptive", "columns": ["age"]},
                                {"test": "pearson", "columns": ["age", "score"]},
                            ]
                        }
                    )
                },
            ),
            ("research", paper, {"document_type": "empirical", "reading_order": "single"}),
        ]
        jobs = {}
        for pipeline, path, data in requests:
            with path.open("rb") as stream:
                response = client.post(
                    f"/pipelines/{pipeline}",
                    files={"file": (path.name, stream)},
                    data=data,
                )
            assert response.status_code == 202, response.text
            jobs[pipeline] = response.json()["id"]
            print(f"Submitted {pipeline}: {jobs[pipeline]}", flush=True)
        results = {}
        deadline = time.monotonic() + 1800
        while len(results) < 3 and time.monotonic() < deadline:
            running = 0
            snapshot = {job["id"]: job for job in client.get("/jobs").json()}
            for pipeline, jid in jobs.items():
                job = snapshot[jid]
                running += job["status"] == "running"
                if job["status"] in {"completed", "failed"} and pipeline not in results:
                    results[pipeline] = job
                    print(
                        f"{pipeline}: {job['status']} {job.get('error') or ''}",
                        flush=True,
                    )
            assert running <= 1, "More than one heavy job running"
            if len(results) < 3:
                time.sleep(2)
        (root / "http_results.json").write_text(json.dumps(results, indent=2))
        assert len(results) == 3, "Timed out waiting for jobs"
        for pipeline, job in results.items():
            assert job["status"] == "completed", job
            directory = root / pipeline
            directory.mkdir()
            for artifact in job["artifacts"]:
                response = client.get(artifact["url"])
                response.raise_for_status()
                (directory / artifact["name"]).write_bytes(response.content)
        cards = json.loads((root / "flashcards/flashcards.json").read_text())[
            "flashcards"
        ]
        assert 1 <= len(cards) <= 3
        with (root / "flashcards/flashcards.csv").open(newline="") as stream:
            assert len(list(csv.DictReader(stream))) == len(cards)
        stats = json.loads((root / "dataset/statistics.json").read_text())
        assert "R version" in stats["engine"]
        assert stats["results"][0]["summary"]["age"]["mean"] == 25.5
        assert not any("error" in r for r in stats["results"])
        interpretations = json.loads((root / "dataset/interpretation.json").read_text())
        assert len(interpretations) == 2 and all(
            "explanation" in i for i in interpretations
        )
        wb = load_workbook(root / "dataset/cleaned.xlsx", read_only=True)
        assert wb.active["D2"].value.strftime("%d/%m/%Y") == "03/04/2026"
        assert wb.active["D2"].number_format == "dd/mm/yyyy"
        wb.close()
        evidence = json.loads((root / "research/evidence.json").read_text())["evidence"]
        quality = json.loads((root / "research/research_quality.json").read_text())
        assert quality["status"] == "completed", quality
        assert results["research"]["research"]["status"] == "completed"
        assert evidence and {e["page"] for e in evidence} == {1, 2}
        for e in evidence:
            source = " ".join(page_texts[e["page"] - 1])
            assert " ".join(e["quote"].split()) in source
            assert " ".join(e["value"].split()) in " ".join(e["quote"].split())
        assert any("120" in e["quote"] for e in evidence)
        summary = {
            "passed": True,
            "jobs": jobs,
            "flashcards": len(cards),
            "research_evidence": len(evidence),
            "R_checks": "descriptive mean and correlation; real local computation",
            "serial_worker": True,
        }
        (root / "acceptance.json").write_text(json.dumps(summary, indent=2))
        print(f"ACCEPTANCE PASSED: {root}", flush=True)


if __name__ == "__main__":
    main()
