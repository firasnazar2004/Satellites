"""Pydantic models for flashcard generation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Flashcard(BaseModel):
    """A single generated flashcard."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    difficulty: Literal["easy", "medium", "hard"]


class FlashcardResponse(BaseModel):
    """Structured response returned by the language model."""

    model_config = ConfigDict(extra="forbid")

    flashcards: list[Flashcard] = Field(min_length=1)
