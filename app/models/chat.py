"""Validated, text-only chat request contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_CHAT_MESSAGES = 24
MAX_CHAT_MESSAGE_CHARS = 8_000
MAX_CHAT_TOTAL_CHARS = 32_000
MAX_CHAT_MEMORIES = 100
MAX_CHAT_MEMORY_CHARS = 500
MAX_CHAT_MEMORY_TOTAL_CHARS = 8_000
MAX_CHAT_MEMORY_ID_CHARS = 128


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


class ChatMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=MAX_CHAT_MEMORY_ID_CHARS)
    content: str = Field(min_length=1, max_length=MAX_CHAT_MEMORY_CHARS)

    @field_validator("id", "content")
    @classmethod
    def values_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Memory fields cannot be blank")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(
        min_length=1,
        max_length=MAX_CHAT_MESSAGES,
    )
    memories: list[ChatMemory] = Field(
        default_factory=list,
        max_length=MAX_CHAT_MEMORIES,
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
        if (
            sum(len(memory.content) for memory in self.memories)
            > MAX_CHAT_MEMORY_TOTAL_CHARS
        ):
            raise ValueError(
                "Persistent memory content cannot exceed "
                f"{MAX_CHAT_MEMORY_TOTAL_CHARS} characters"
            )
        return self
