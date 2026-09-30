"""Small Ollama adapter for schema-constrained local LLM responses."""

from typing import TypeVar

import ollama
from pydantic import BaseModel


StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


def generate_structured(
    prompt: str,
    response_model: type[StructuredResponse],
    *,
    model: str = "qwen3:8b",
    system_prompt: str | None = None,
) -> StructuredResponse:
    """Generate a response with Ollama and validate it as a Pydantic model."""

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = ollama.chat(
        model=model,
        messages=messages,
        format=response_model.model_json_schema(),
        options={"temperature": 0},
        think=False,
    )

    return response_model.model_validate_json(response.message.content)
