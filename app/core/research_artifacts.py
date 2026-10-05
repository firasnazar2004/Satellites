"""Read-only visibility of research checkpoints, including unsuccessful jobs."""

from app.models.research import ResearchOutcome
from app.pipelines.research_reporting import RESEARCH_ARTIFACTS


def research_artifacts(job):
    if job.pipeline != "research":
        return {}
    return {name: job.output_dir / name for name in RESEARCH_ARTIFACTS
            if (job.output_dir / name).is_file()
            and (job.output_dir / name).resolve().parent == job.output_dir.resolve()}


def research_quality(job):
    if job.pipeline != "research" or job.status not in {"completed", "failed"}:
        return None
    path = research_artifacts(job).get("research_quality.json")
    if path is None:
        if job.status == "failed":
            return ResearchOutcome(
                status="failed", processing_status="failed",
                processing_error=job.error or "Research job failed before quality assessment",
                reasons=["No research-quality artifact was written"],
            )
        # Existing completed v1 jobs have no quality assessment.
        return None
    try:
        quality = ResearchOutcome.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ResearchOutcome(status="failed", processing_status="failed",
            processing_error="Quality artifact unreadable or invalid",
            reasons=["Processing ended without a valid research-quality artifact"])
    if quality.schema_version in {"2.2", "2.3"} and quality.report_kind == "unavailable":
        report_path = job.output_dir / "research_report.md"
        if report_path.is_file():
            try:
                heading = report_path.read_text(encoding="utf-8")[:200].casefold()
            except OSError:
                heading = ""
            quality.report_availability = "partial" if quality.status != "completed" else "available"
            if "limited overview only" in heading:
                quality.report_kind = "limited_overview"
            elif "# research report" in heading:
                quality.report_kind = ("validated_report" if quality.status == "completed"
                                       else "partial_report")
            else:
                quality.report_availability = "unavailable"
                quality.report_kind = "unavailable"
    if job.status == "failed":
        quality.status = "failed"
        quality.processing_status = "failed"
        quality.processing_error = job.error or "Job execution failed before completion"
        quality.reasons.append("Available artifacts are checkpoints from an execution that failed")
        report_path = job.output_dir / "research_report.md"
        if report_path.is_file():
            quality.report_availability = "partial"
            try:
                heading = report_path.read_text(encoding="utf-8")[:160]
            except OSError:
                heading = ""
            quality.report_kind = ("limited_overview" if "limited overview only" in heading.casefold()
                                   else "partial_report")
        else:
            quality.report_availability = "unavailable"
            quality.report_kind = "unavailable"
    return quality
