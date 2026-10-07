"""Research processor orchestrating serial, auditable stages in the existing worker."""
import json
from pathlib import Path

import ollama
import httpx
from pydantic import ValidationError

from app.core.llm import generate_structured
from app.core.research_config import CONFIG
from app.models.research_pipeline import EvidenceStore, ResearchDiagnostics
from app.pipelines.research_context import build_context_windows
from app.pipelines.research_evidence import consolidate_evidence, extract_candidates, profile_document, refine_profile
from app.pipelines.research_pdf import ResearchFailure, extract_source_map, validate_pdf
from app.pipelines.research_report import build_report_plan, render_markdown, synthesize_report
from app.pipelines.research_validation import adjudicate_scope, calculate_coverage, enforce_coverage, is_unambiguous_verbatim, needs_scope_check, semantic_evidence, validate_candidate


def _write(path: Path, value) -> Path:
    path.write_text(value.model_dump_json(indent=2) if hasattr(value, "model_dump_json") else json.dumps(value, indent=2), encoding="utf-8")
    return path


def process_research_file(input_path: Path, output_dir: Path) -> list[Path]:
    diagnostics = ResearchDiagnostics()
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostic_path = output_dir / "research_diagnostics.json"
    rejected_path = output_dir / "research_rejections.jsonl"
    artifacts = []
    raw = ""

    def reject(stage, reason, model_output, attempt):
        with rejected_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"schema_version": 1, "stage": stage, "attempt": attempt, "reason": reason, "model_output": model_output}, ensure_ascii=False, default=str) + "\n")

    def ask(prompt, response_model):
        nonlocal raw
        raw = ""
        diagnostics.model_calls[response_model.__name__] = diagnostics.model_calls.get(response_model.__name__, 0) + 1
        _write(diagnostic_path, diagnostics)
        try:
            return generate_structured(prompt, response_model, model=CONFIG.model, num_ctx=CONFIG.num_ctx, num_predict=CONFIG.num_predict, on_raw=lambda value: _capture(value))
        except ollama.ResponseError as exc:
            reject("model_call", str(exc), raw, 1)
            code = "MODEL_UNAVAILABLE" if exc.status_code in {404, 503} else "MODEL_REQUEST_FAILURE"
            raise ResearchFailure(code, str(exc)) from exc
        except (httpx.ConnectError, httpx.TimeoutException, ConnectionError, TimeoutError) as exc:
            reject("model_call", str(exc), raw, 1)
            raise ResearchFailure("MODEL_UNAVAILABLE", str(exc)) from exc
        except httpx.HTTPError as exc:
            reject("model_call", str(exc), raw, 1)
            raise ResearchFailure("MODEL_REQUEST_FAILURE", str(exc)) from exc
        except (ValidationError, ValueError) as exc:
            reject("model_schema", str(exc), raw, 1)
            raise ResearchFailure("MODEL_SCHEMA_FAILURE", str(exc)) from exc

    def _capture(value):
        nonlocal raw
        raw = value

    def stage(name):
        if diagnostics.current_stage not in diagnostics.completed_stages and diagnostics.current_stage != name:
            diagnostics.completed_stages.append(diagnostics.current_stage)
        diagnostics.current_stage = name
        _write(diagnostic_path, diagnostics)

    try:
        stage("PDF_VALIDATION")
        pdf = validate_pdf(input_path, CONFIG.max_pages)
        stage("SOURCE_EXTRACTION")
        source = extract_source_map(input_path, CONFIG.max_pages, pdf)
        diagnostics.extraction = source.metadata.model_dump()
        artifacts.append(_write(output_dir / "research_source_map.json", source))
        stage("CONTEXT_BUILDING")
        windows = build_context_windows(source, CONFIG.window_chars, CONFIG.window_overlap_blocks)
        if not windows:
            raise ResearchFailure("SOURCE_CONTEXT_FAILURE", "No usable body context")
        stage("DOCUMENT_PROFILE")
        profile = profile_document(source, ask)
        artifacts.append(_write(output_dir / "research_profile.json", profile))
        stage("EVIDENCE_EXTRACTION")
        candidates = extract_candidates(windows, source, ask, reject)
        diagnostics.evidence["candidates"] = len(candidates)
        stage("EVIDENCE_VALIDATION")
        accepted = []
        for candidate in candidates:
            try:
                validate_candidate(candidate, source)
                if (profile.primary_kind == "review" and candidate.source_scope == "current_study") or needs_scope_check(candidate, source):
                    attribution = adjudicate_scope(candidate, source, ask)
                    if attribution.source_scope == "unclear":
                        reject("scope_validation", f"{attribution.source_scope}: {attribution.reason}", candidate.model_dump(), 1)
                        continue
                    candidate.source_scope = attribution.source_scope
                decision = (
                    semantic_evidence(candidate, source, ask)
                    if not is_unambiguous_verbatim(candidate, source)
                    else None
                )
                if decision is None:
                    candidate.support = "direct"
                    accepted.append(candidate)
                    continue
                candidate.support = decision.support
                if decision.support != "direct":
                    reject("evidence_validation", f"{decision.support}: {decision.reason}", candidate.model_dump(), 1)
                    continue
                accepted.append(candidate)
            except ResearchFailure as exc:
                reject("evidence_validation", str(exc), candidate.model_dump(), 1)
        diagnostics.evidence.update(accepted=len(accepted), rejected=len(candidates)-len(accepted))
        if not accepted:
            raise ResearchFailure("EVIDENCE_VALIDATION_FAILURE", "No directly supported evidence")
        stage("EVIDENCE_CONSOLIDATION")
        evidence = consolidate_evidence(accepted)
        profile = refine_profile(profile, evidence)
        _write(output_dir / "research_profile.json", profile)
        artifacts.append(_write(output_dir / "research_evidence.json", EvidenceStore(evidence=evidence)))
        stage("REPORT_PLANNING")
        plan = build_report_plan(profile, evidence, CONFIG.packet_chars)
        diagnostics.report["planning"] = {"mandatory": sum(len(p.mandatory) for p in plan.packets), "supporting": sum(len(p.supporting) for p in plan.packets), "excluded": sum(len(p.excluded) for p in plan.packets)}
        artifacts.append(_write(output_dir / "research_plan.json", plan))
        stage("SECTION_SYNTHESIS")
        report = synthesize_report(source.source_filename, profile, plan, evidence, ask, reject, CONFIG.synthesis_retries)
        stage("REPORT_VALIDATION")
        # All exact sentences have passed deterministic and semantic checks above.
        stage("FINAL_COVERAGE")
        coverage = calculate_coverage(report, plan, evidence)
        diagnostics.report["coverage"] = coverage.model_dump()
        artifacts.append(_write(output_dir / "research_coverage.json", coverage))
        enforce_coverage(coverage)
        artifacts.append(_write(output_dir / "research_report.json", report))
        stage("RENDERING")
        markdown = render_markdown(report, evidence, source)
        report_path = output_dir / "research_report.md"
        report_path.write_text(markdown, encoding="utf-8")
        artifacts.append(report_path)
        diagnostics.completed_stages.append("RENDERING")
        diagnostics.current_stage = "COMPLETED"
        artifacts.append(_write(diagnostic_path, diagnostics))
        if rejected_path.exists():
            artifacts.append(rejected_path)
        return artifacts
    except Exception as exc:
        diagnostics.failed_stage = diagnostics.current_stage
        diagnostics.failure = {"code": exc.code if isinstance(exc, ResearchFailure) else "INTERNAL_ERROR", "message": str(exc)}
        _write(diagnostic_path, diagnostics)
        raise
