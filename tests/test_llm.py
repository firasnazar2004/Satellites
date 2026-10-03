"""Tests for the schema-constrained Ollama adapter."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.llm import generate_structured
from app.models.flashcard import FlashcardResponse


class StructuredGenerationTests(unittest.TestCase):
    @patch("app.core.llm.ollama.Client.chat")
    def test_response_is_validated_into_requested_model(self, chat_mock) -> None:
        chat_mock.return_value = SimpleNamespace(
            message=SimpleNamespace(
                content=(
                    '{"flashcards":[{"front":"Question","back":"Answer",'
                    '"topic":"Test","difficulty":"easy"}]}'
                )
            )
        )

        result = generate_structured(
            "Generate a card",
            FlashcardResponse,
            system_prompt="Use only supplied facts",
        )

        self.assertIsInstance(result, FlashcardResponse)
        self.assertEqual(result.flashcards[0].front, "Question")
        call_arguments = chat_mock.call_args.kwargs
        self.assertEqual(call_arguments["model"], "qwen3:8b")
        self.assertEqual(
            call_arguments["format"], FlashcardResponse.model_json_schema()
        )
        self.assertFalse(call_arguments["think"])


if __name__ == "__main__":
    unittest.main()
