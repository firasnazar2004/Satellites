"""Command-line interface for local processing pipelines."""

import argparse
import sys
from pathlib import Path
from typing import Sequence

from app.core.execution import execute
from app.core.jobs import create_job, run_job
from app.core.llm import DEFAULT_MODEL
from app.models.analysis import AnalysisPlan
from app.models.dataset import SourceProfile
from app.models.job import PipelineType
from app.pipelines.flashcards import (
    DEFAULT_CARDS_PER_CHUNK,
    DEFAULT_MAX_CHUNK_CHARS,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-data-assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    flashcards = subparsers.add_parser(
        "flashcards",
        help="Generate flashcards from a UTF-8 TXT file",
    )
    flashcards.add_argument("input", type=Path, help="Path to the source TXT file")
    flashcards.add_argument("--model", default=DEFAULT_MODEL)
    flashcards.add_argument(
        "--cards-per-chunk",
        type=int,
        default=DEFAULT_CARDS_PER_CHUNK,
    )
    flashcards.add_argument(
        "--max-chunk-chars",
        type=int,
        default=DEFAULT_MAX_CHUNK_CHARS,
    )
    flashcards.add_argument(
        "--jobs-root",
        type=Path,
        default=Path("outputs/jobs"),
        help="Directory where job folders are created",
    )

    dataset = subparsers.add_parser(
        "dataset",
        help="Validate and clean a CSV file into Parquet",
    )
    dataset.add_argument("input", type=Path, help="Path to the source CSV file")
    dataset.add_argument(
        "--date-order",
        choices=["dmy", "mdy", "ymd"],
        default="dmy",
        help="How to interpret non-ISO dates (default: dmy)",
    )
    dataset.add_argument(
        "--trust-date-order",
        action="store_true",
        help="Resolve ambiguous day/month dates using --date-order instead of quarantining",
    )
    dataset.add_argument(
        "--jobs-root",
        type=Path,
        default=Path("outputs/jobs"),
        help="Directory where job folders are created",
    )
    dataset.add_argument(
        "--analysis-plan", type=Path, help="JSON file listing tests and columns"
    )
    dataset.add_argument(
        "--profile",
        type=Path,
        help="JSON source profile overriding date and record options",
    )
    dataset.add_argument(
        "--no-interpret",
        action="store_true",
        help="Run deterministic stages without Qwen interpretation",
    )
    dataset.add_argument(
        "--record-mode", choices=["single_line", "standard"], default="single_line"
    )
    research = subparsers.add_parser(
        "research", help="Extract validated PDF evidence and a cited summary"
    )
    research.add_argument("input", type=Path)
    research.add_argument("--max-chunk-chars", type=int, default=3000)
    research.add_argument("--document-type", choices=["auto", "empirical", "review", "theoretical"], default="auto")
    research.add_argument("--reading-order", choices=["auto", "single", "two", "three"], default="auto")
    research.add_argument("--jobs-root", type=Path, default=Path("outputs/jobs"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "flashcards":
        return _run_flashcard_job(args)
    if args.command == "dataset":
        return _run_dataset_job(args)
    if args.command == "research":
        return _run_pipeline(
            PipelineType.RESEARCH, args, {"max_chunk_chars": args.max_chunk_chars,
                "document_type": args.document_type, "reading_order": args.reading_order}
        )

    raise AssertionError(f"Unhandled command: {args.command}")


def _run_flashcard_job(args: argparse.Namespace) -> int:
    return _run_pipeline(
        PipelineType.FLASHCARDS,
        args,
        {
            "model": args.model,
            "max_chunk_chars": args.max_chunk_chars,
            "cards_per_chunk": args.cards_per_chunk,
        },
    )


def _run_pipeline(pipeline, args, options):
    job = None
    try:
        job = create_job(
            pipeline,
            args.input,
            jobs_root=args.jobs_root,
        )
        processor = lambda source, output: execute(
            pipeline.value, source, output, options
        )
        job = run_job(job, processor)
    except Exception as exc:
        print(f"{pipeline.value} job failed: {exc}", file=sys.stderr)
        if job is not None:
            print(
                f"Failure details: {job.output_dir / 'job.json'}",
                file=sys.stderr,
            )
        return 1

    print(f"Job {job.id} completed")
    for artifact in job.artifacts:
        print(artifact)
    if pipeline == PipelineType.RESEARCH:
        from app.core.research_artifacts import research_quality

        quality = research_quality(job)
        if quality:
            print(f"Research quality: {quality.status}")
            for reason in quality.missing_coverage + quality.reasons:
                print(f"- {reason}")
            if quality.status != "completed":
                return 2
    return 0


def _run_dataset_job(args: argparse.Namespace) -> int:
    try:
        plan = (
            AnalysisPlan.model_validate_json(args.analysis_plan.read_text())
            if args.analysis_plan
            else AnalysisPlan()
        )
        profile = (
            SourceProfile.model_validate_json(args.profile.read_text())
            if args.profile
            else None
        )
        if profile:
            args.date_order = profile.date_order
            args.trust_date_order = profile.trust_date_order
            args.record_mode = profile.record_mode
    except Exception as exc:
        print(f"Invalid analysis plan: {exc}", file=sys.stderr)
        return 1
    return _run_pipeline(
        PipelineType.DATASET,
        args,
        {
            "date_order": args.date_order,
            "trust_date_order": args.trust_date_order,
            "record_mode": args.record_mode,
            "plan": plan.model_dump(),
            "interpret": not args.no_interpret,
            "source_profile": profile.model_dump() if profile else None,
        },
    )
