from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.base import ModelProtocolError, ModelProviderError
from app.llm.openai_compatible import OpenAICompatibleProvider

TOOLS = [{"type": "function", "function": {"name": "get_service_health", "parameters": {}}}]
MESSAGES = [{"role": "user", "content": "Inspect payments-api"}]


def make_response(*, arguments: str = '{"service":"payments-api"}') -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="get_service_health", arguments=arguments
                            ),
                        )
                    ],
                )
            )
        ]
    )


@pytest.mark.asyncio
async def test_openai_adapter_uses_configured_endpoint_and_model() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://example.test/v1", api_key="test-secret", model="test-model"
    )
    provider.client.chat.completions.create = AsyncMock(return_value=make_response())

    turn = await provider.complete(MESSAGES, TOOLS)

    call = provider.client.chat.completions.create.call_args
    assert call.kwargs["model"] == "test-model"
    assert provider.client.base_url.host == "example.test"
    assert turn.tool_calls[0].arguments == {"service": "payments-api"}


@pytest.mark.asyncio
async def test_openai_adapter_rejects_malformed_tool_arguments() -> None:
    provider = OpenAICompatibleProvider("https://example.test/v1", "test-secret", "test-model")
    provider.client.chat.completions.create = AsyncMock(return_value=make_response(arguments="{"))

    with pytest.raises(ModelProtocolError, match="tool arguments"):
        await provider.complete(MESSAGES, TOOLS)


@pytest.mark.asyncio
async def test_openai_adapter_hides_api_key_from_provider_errors() -> None:
    provider = OpenAICompatibleProvider("https://example.test/v1", "test-secret", "test-model")
    provider.client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("test-secret leaked")
    )

    with pytest.raises(ModelProviderError) as raised:
        await provider.complete(MESSAGES, TOOLS)

    assert "test-secret" not in str(raised.value)
