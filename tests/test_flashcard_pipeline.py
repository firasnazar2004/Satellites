"""Tests for TXT cleanup, chunking, validation, and CSV output."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.flashcard import Flashcard, FlashcardResponse
from app.pipelines.flashcards import chunk_text, process_flashcard_file


class FlashcardPipelineTests(unittest.TestCase):
    def test_chunk_text_preserves_all_words_within_limit(self) -> None:
        text = "First short paragraph.\n\nSecond paragraph has several words."

        chunks = chunk_text(text, max_chars=25)

        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= 25 for chunk in chunks))
        self.assertEqual(
            " ".join(" ".join(chunks).split()),
            " ".join(text.split()),
        )

    @patch("app.pipelines.flashcards.generate_structured")
    def test_pipeline_writes_validated_deduplicated_csv(self, generate_mock) -> None:
        duplicate = Flashcard(
            front="What is ATP?",
            back="A cellular energy carrier.",
            topic="Biology",
            difficulty="easy",
        )
        generate_mock.side_effect = [
            FlashcardResponse(flashcards=[duplicate]),
            FlashcardResponse(
                flashcards=[
                    duplicate,
                    Flashcard(
                        front="Where is ATP produced?",
                        back="Primarily in mitochondria.",
                        topic="Biology",
                        difficulty="medium",
                    ),
                ]
            ),
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "biology.txt"
            output_dir = root / "output"
            output_dir.mkdir()
            input_path.write_text("First section.\n\nSecond section.", encoding="utf-8")

            artifacts = process_flashcard_file(
                input_path,
                output_dir,
                max_chunk_chars=16,
                cards_per_chunk=1,
            )

            with artifacts[0].open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["Front"], "What is ATP?")
            self.assertEqual(rows[0]["Source"], "biology.txt")
            self.assertTrue((output_dir / "flashcards.json").is_file())
            self.assertEqual(generate_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
