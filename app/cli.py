"""Command-line interface for local processing pipelines."""

import argparse
import sys
from functools import partial
from pathlib import Path
from typing import Sequence

from app.core.jobs import create_job, run_job
from app.models.job import PipelineType
from app.pipelines.flashcards import (
    DEFAULT_CARDS_PER_CHUNK,
    DEFAULT_MAX_CHUNK_CHARS,
    process_flashcard_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-data-assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    flashcards = subparsers.add_parser(
        "flashcards",
        help="Generate flashcards from a UTF-8 TXT file",
    )
    flashcards.add_argument("input", type=Path, help="Path to the source TXT file")
    flashcards.add_argument("--model", default="qwen3:8b")
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "flashcards":
        return _run_flashcard_job(args)

    raise AssertionError(f"Unhandled command: {args.command}")


def _run_flashcard_job(args: argparse.Namespace) -> int:
    job = None
    try:
        job = create_job(
            PipelineType.FLASHCARDS,
            args.input,
            jobs_root=args.jobs_root,
        )
        processor = partial(
            process_flashcard_file,
            model=args.model,
            max_chunk_chars=args.max_chunk_chars,
            cards_per_chunk=args.cards_per_chunk,
        )
        job = run_job(job, processor)
    except Exception as exc:
        print(f"Flashcard job failed: {exc}", file=sys.stderr)
        if job is not None:
            print(
                f"Failure details: {job.output_dir / 'job.json'}",
                file=sys.stderr,
            )
        return 1

    print(f"Job {job.id} completed")
    for artifact in job.artifacts:
        print(artifact)
    return 0
