"""Read-only replay of saved research artifacts through current validators."""

import argparse
import json
from pathlib import Path

from app.models.research import GroundedEvidence, ResearchNarrative, ResearchOutcome, SourcePassage
from app.core.research_artifacts import research_quality
from app.models.job import Job, JobStatus, PipelineType
from app.pipelines.research_reporting import (
    build_synthesis_payload, render_report, select_evidence, validate_narrative_issues,
)


def replay_saved_artifacts(artifact_dir: Path, output_dir: Path) -> dict:
    """Validate a compatible artifact set and write only to ``output_dir``.

    The source PDF is deliberately never opened. Compatibility is established
    from schema/run metadata, source filename, passage IDs and exact quote spans.
    """
    artifact_dir = artifact_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir == artifact_dir or artifact_dir in output_dir.parents:
        raise ValueError("Replay output must be outside the historical artifact directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    required = ("request.json", "evidence.json", "passages.json", "synthesis.json",
                "research_quality.json", "research_diagnostics.json", "research_events.jsonl")
    missing = [name for name in required if not (artifact_dir / name).is_file()]
    if missing:
        raise ValueError("Missing replay artifacts: " + ", ".join(missing))

    def load(name):
        return json.loads((artifact_dir / name).read_text(encoding="utf-8"))

    request, evidence_doc, raw_passages = load("request.json"), load("evidence.json"), load("passages.json")
    synthesis, quality_doc, diagnostics = (load("synthesis.json"), load("research_quality.json"),
                                            load("research_diagnostics.json"))
    versions = {evidence_doc.get("schema_version"), synthesis.get("schema_version"),
                quality_doc.get("schema_version")}
    if len(versions) != 1 or not versions <= {"2.2", "2.3"}:
        raise ValueError(f"Incompatible artifact schema versions: {sorted(map(str, versions))}")
    if request.get("pipeline") != "research":
        raise ValueError("request.json is not a research run")
    if Path(request.get("input", "")).name != evidence_doc.get("source"):
        raise ValueError("Request source and evidence source names differ")
    source_hash = diagnostics.get("configuration", {}).get("source_sha256")
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        raise ValueError("Research diagnostics do not contain a source hash")
    event_lines = (artifact_dir / "research_events.jsonl").read_text(
        encoding="utf-8").splitlines()
    if not event_lines:
        raise ValueError("Research event log is empty")
    first_event = json.loads(event_lines[0])
    event_hash = first_event.get("configuration", {}).get("source_sha256")
    if event_hash not in {source_hash, "unavailable"}:
        raise ValueError("Event and diagnostics source hashes differ")

    passages = [SourcePassage.model_validate({key: value for key, value in item.items()
                 if key in SourcePassage.model_fields}) for item in raw_passages]
    passage_by_id = {item.id: item for item in passages}
    records = [GroundedEvidence.model_validate(item) for item in evidence_doc.get("evidence", [])]
    if len({item.id for item in records}) != len(records):
        raise ValueError("Evidence IDs are not unique")
    for record in records:
        source = passage_by_id.get(record.passage_id)
        if source is None or source.page != record.page or source.text != record.quote:
            raise ValueError(f"Evidence provenance mismatch for {record.id}")
        if not 0 <= record.value_start <= record.value_end <= len(record.quote):
            raise ValueError(f"Invalid evidence value span for {record.id}")
        if record.quote[record.value_start:record.value_end] != record.value:
            raise ValueError(f"Evidence literal span mismatch for {record.id}")

    current_selected = select_evidence(records, evidence_doc.get("document_type", "unknown"))
    current_selected_ids = [item.id for item in current_selected]
    records_by_id = {item.id: item for item in records}
    saved_selected_ids = synthesis.get("selected_ids", [])
    if not set(saved_selected_ids) <= records_by_id.keys():
        raise ValueError("Saved synthesis references evidence absent from evidence.json")
    selected = [records_by_id[item] for item in saved_selected_ids]
    provided_ids = set(synthesis.get("provided_evidence_ids", saved_selected_ids))
    replay_selected = [item for item in selected if item.id in provided_ids]
    payload = build_synthesis_payload(replay_selected, passages, evidence_doc.get("metadata", []))
    drafts = []
    for attempt in synthesis.get("attempts", []):
        draft = attempt.get("narrative")
        if draft is None:
            continue
        narrative = ResearchNarrative.model_validate(draft)
        issues = validate_narrative_issues(narrative, payload)
        drafts.append({"attempt": attempt.get("attempt"), "issue_codes": sorted(
            {item["code"] for item in issues}), "issues": issues})
    latest = None
    if synthesis.get("attempts"):
        for attempt in reversed(synthesis["attempts"]):
            if attempt.get("narrative"):
                latest = ResearchNarrative.model_validate(attempt["narrative"])
                break
    execution_status = (JobStatus.FAILED if quality_doc.get("processing_status") == "failed"
                        else JobStatus.COMPLETED)
    replay_job = Job(pipeline=PipelineType.RESEARCH, input_path=Path(request["input"]),
                     output_dir=artifact_dir, status=execution_status,
                     error=quality_doc.get("processing_error"))
    quality = research_quality(replay_job)
    if quality is None:
        quality = ResearchOutcome.model_validate(quality_doc)
    report = render_report(evidence_doc.get("source", "saved-source"), replay_selected, passages,
                           evidence_doc.get("metadata", []), quality, latest)
    (output_dir / "replay_report.md").write_text(report, encoding="utf-8")
    result = {"source_sha256": source_hash, "schema_version": next(iter(versions)),
              "passages": len(passages), "evidence": len(records),
              "saved_selected_ids": saved_selected_ids,
              "current_selected_ids": current_selected_ids,
              "selection_matches_saved": current_selected_ids == saved_selected_ids,
              "provided_ids": [item["evidence_id"] for item in payload if "evidence_id" in item],
              "drafts": drafts,
              "replay_report": str(output_dir / "replay_report.md"),
              "source_pdf_opened": False}
    (output_dir / "replay_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    result = replay_saved_artifacts(args.artifact_dir, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
