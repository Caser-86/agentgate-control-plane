from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ModelTurn:
    assistant_message: dict[str, object]
    text: str | None
    tool_calls: tuple[ToolCall, ...]


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ModelTurn: ...


class ModelProtocolError(RuntimeError):
    pass


class ModelProviderError(RuntimeError):
    pass
