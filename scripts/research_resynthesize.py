"""Replay report planning and synthesis from validated research artifacts."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.llm import generate_structured
from app.core.research_config import CONFIG
from app.core.heavy_resource import HEAVY_RESOURCE
from app.models.research_pipeline import DocumentProfile, EvidenceStore, ResearchSourceMap
from app.pipelines.research_report import build_report_plan, render_markdown, synthesize_report
from app.pipelines.research_validation import calculate_coverage, enforce_coverage
from scripts.research_smoke import check


def main() -> int:
    previous = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    expectation = json.loads(Path(sys.argv[3]).read_text())
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ("research_source_map.json", "research_evidence.json", "research_profile.json"):
        shutil.copy2(previous / filename, destination / filename)
    source = ResearchSourceMap.model_validate_json((destination / "research_source_map.json").read_text())
    evidence = EvidenceStore.model_validate_json((destination / "research_evidence.json").read_text()).evidence
    profile = DocumentProfile.model_validate_json((destination / "research_profile.json").read_text())
    plan = build_report_plan(profile, evidence, CONFIG.packet_chars)
    (destination / "research_plan.json").write_text(plan.model_dump_json(indent=2))

    def ask(prompt, response_model):
        return generate_structured(prompt, response_model, model=CONFIG.model, num_ctx=CONFIG.num_ctx, num_predict=CONFIG.num_predict)

    def reject(stage, reason, model_output, attempt):
        with (destination / "research_rejections.jsonl").open("a") as stream:
            stream.write(json.dumps({"stage": stage, "reason": reason, "model_output": model_output, "attempt": attempt}) + "\n")

    with HEAVY_RESOURCE.hold():
        report = synthesize_report(source.source_filename, profile, plan, evidence, ask, reject, CONFIG.synthesis_retries)
    coverage = calculate_coverage(report, plan, evidence)
    enforce_coverage(coverage)
    (destination / "research_coverage.json").write_text(coverage.model_dump_json(indent=2))
    (destination / "research_report.json").write_text(report.model_dump_json(indent=2))
    (destination / "research_report.md").write_text(render_markdown(report, evidence, source))
    errors = check(destination, expectation)
    print(f"{'PASS' if not errors else 'FAIL'} {errors}; artifacts: {destination}")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
