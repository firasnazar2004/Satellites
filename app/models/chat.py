"""Validated, text-only chat request contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CHAT_MESSAGES = 24
MAX_CHAT_MESSAGE_CHARS = 8_000
MAX_CHAT_TOTAL_CHARS = 32_000


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)

    @field_validator("content")
    @classmethod
    def content_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content cannot be blank")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGES,
    )

    @model_validator(mode="after")
    def validate_conversation(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must have role 'user'")
        if (
            sum(len(message.content) for message in self.messages)
            > MAX_CHAT_TOTAL_CHARS
        ):
            raise ValueError(
                f"Conversation content cannot exceed {MAX_CHAT_TOTAL_CHARS} characters"
            )
        return self
