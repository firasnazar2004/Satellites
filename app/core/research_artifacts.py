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
    if job.status == "failed":
        if quality.status == "completed":
            quality.status = "partial"
        quality.processing_status = "failed"
        quality.extraction_complete = False
        quality.processing_error = job.error or "Job execution failed before completion"
        quality.reasons.append("Available artifacts are checkpoints from an execution that failed")
    return quality
