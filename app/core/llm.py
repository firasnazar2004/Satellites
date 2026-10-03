"""Small Ollama adapter for schema-constrained local LLM responses."""

import time
from typing import TypeVar

import ollama
from pydantic import BaseModel

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"


def generate_structured(
    prompt: str,
    response_model: type[StructuredResponse],
    *,
    model: str = DEFAULT_MODEL,
    system_prompt: str | None = None,
) -> StructuredResponse:
    """Generate a response with Ollama and validate it as a Pydantic model."""

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    client = ollama.Client(host=OLLAMA_BASE_URL, timeout=300, trust_env=False)
    for attempt in range(3):
        try:
            response = client.chat(
                model=model,
                messages=messages,
                format=response_model.model_json_schema(),
                options={"temperature": 0, "num_ctx": 4096, "num_predict": 1800},
                think=False,
                keep_alive="2m",
            )
            break
        except ollama.ResponseError as exc:
            if exc.status_code not in {500, 502, 503} or attempt == 2:
                raise
            time.sleep(2**attempt)

    if (
        not response.message.content
        or getattr(response, "done_reason", None) == "length"
    ):
        raise ValueError("Ollama returned empty or truncated JSON; reduce chunk size")
    return response_model.model_validate_json(response.message.content)


def unload_models() -> None:
    """Release resident local models before deterministic memory-heavy stages."""
    client = ollama.Client(host=OLLAMA_BASE_URL, timeout=60, trust_env=False)
    for model in client.ps().models:
        client.generate(model=model.model, keep_alive=0)
    deadline = time.monotonic() + 60
    while client.ps().models:
        if time.monotonic() > deadline:
            raise TimeoutError("Ollama did not release model memory within a minute")
        time.sleep(0.25)
