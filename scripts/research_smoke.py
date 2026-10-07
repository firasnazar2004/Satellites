"""Run real Ollama research acceptance PDFs and check human-authored facts."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.execution import execute
from app.core.jobs import create_job, run_job
from app.models.job import PipelineType


def check(out: Path, expected: dict) -> list[str]:
    source = json.loads((out / "research_source_map.json").read_text())
    evidence = json.loads((out / "research_evidence.json").read_text())["evidence"]
    report = json.loads((out / "research_report.json").read_text())
    profile = json.loads((out / "research_profile.json").read_text())
    coverage = json.loads((out / "research_coverage.json").read_text())
    blocks = {b["block_id"]: b for b in source["blocks"]}
    cited = {eid for section in report["sections"] for sentence in section["sentences"] for eid in sentence["evidence_ids"]}
    errors = []
    for fact in expected.get("required_facts", []):
        found = any(fact["concept"].casefold() in e["claim"].casefold() and fact["value"].casefold() in e["claim"].casefold() and e["evidence_id"] in cited and any(blocks[ref]["page"] == fact["page"] for ref in e["source_refs"]) for e in evidence)
        if not found:
            errors.append(f"missing fact: {fact}")
    report_text = " ".join(s["text"] for section in report["sections"] for s in section["sentences"])
    for token in expected.get("required_numbers", []):
        if token not in report_text:
            errors.append(f"missing number: {token}")
    for page in expected.get("source_pages", []):
        if not any(b["page"] == page for b in blocks.values()):
            errors.append(f"missing page: {page}")
    for item in expected.get("forbidden_attributions", []):
        if any(item["value"] in e["claim"] and e["source_scope"] == item["scope"] for e in evidence):
            errors.append(f"forbidden attribution: {item}")
    for trait in expected.get("expected_traits", []):
        if not profile["traits"].get(trait):
            errors.append(f"missing trait: {trait}")
    if expected.get("expected_primary_kind") and profile["primary_kind"] != expected["expected_primary_kind"]:
        errors.append(f"primary kind: {profile['primary_kind']} != {expected['expected_primary_kind']}")
    if (coverage["mandatory_missing"] or coverage["mandatory_covered"] != coverage["mandatory_evidence"]
        or coverage["citation_resolution"] != 1 or coverage["invalid_evidence_ids"]
        or coverage["unsupported_numeric_claims"] or coverage["unsupported_sentences"]):
        errors.append(f"coverage gate: {coverage}")
    return errors


def main() -> int:
    corpus = Path(sys.argv[1] if len(sys.argv) > 1 else "research_checks/corpus")
    fixtures = [corpus] if corpus.is_file() else sorted(corpus.glob("*.expect.json"))
    if not fixtures:
        print(f"No expectation files in {corpus}", file=sys.stderr)
        return 2
    failures = 0
    for expectation in fixtures:
        expected = json.loads(expectation.read_text())
        path = Path(expected["pdf_path"]) if expected.get("pdf_path") else expectation.with_name(expectation.name.removesuffix(".expect.json") + ".pdf")
        if not path.is_file():
            print(f"Missing PDF for {expectation}: {path}", file=sys.stderr)
            failures += 1
            continue
        job = create_job(PipelineType.RESEARCH, path)
        try:
            run_job(job, lambda source, out: execute("research", source, out, {}))
            errors = ([f"expected failure {expected['expected_failure']}, but job completed"]
                      if expected.get("expected_failure") else check(job.output_dir, expected))
        except Exception as exc:
            errors = [] if expected.get("expected_failure") and expected["expected_failure"] in str(exc) else [str(exc)]
        print(f"{path.name}: {'PASS' if not errors else 'FAIL'} {errors}; artifacts: {job.output_dir}")
        failures += bool(errors)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
