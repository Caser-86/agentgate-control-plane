import json

import pytest

from app.llm.mock import MockLLMProvider

TOOLS = [
    {
        "type": "function",
        "function": {"name": "get_service_health", "parameters": {}},
    },
    {"type": "function", "function": {"name": "search_logs", "parameters": {}}},
    {"type": "function", "function": {"name": "restart_service", "parameters": {}}},
    {"type": "function", "function": {"name": "rotate_api_key", "parameters": {}}},
]


@pytest.mark.asyncio
async def test_mock_tool_call_ids_are_stable() -> None:
    provider = MockLLMProvider()
    messages = [{"role": "user", "content": "Inspect payments-api"}]

    first = await provider.complete(messages, TOOLS)
    second = await provider.complete(messages, TOOLS)

    assert first.tool_calls[0].id == second.tool_calls[0].id
    assert first.tool_calls[0].name == "get_service_health"


@pytest.mark.asyncio
async def test_mock_follows_degraded_restart_scenario_from_tool_results() -> None:
    provider = MockLLMProvider()
    messages = [
        {
            "role": "user",
            "content": "Investigate payments-api and restore it safely. Do not rotate credentials.",
        }
    ]

    health = await provider.complete(messages, TOOLS)
    messages.append(health.assistant_message)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": health.tool_calls[0].id,
            "name": "get_service_health",
            "content": json.dumps({"service": "payments-api", "health": "degraded"}),
        }
    )
    logs = await provider.complete(messages, TOOLS)
    assert logs.tool_calls[0].name == "search_logs"

    messages.append(logs.assistant_message)
    messages.append(
        {
            "role": "tool",
            "tool_call_id": logs.tool_calls[0].id,
            "name": "search_logs",
            "content": json.dumps({"service": "payments-api", "records": [{"severity": "error"}]}),
        }
    )
    restart = await provider.complete(messages, TOOLS)
    assert restart.tool_calls[0].name == "restart_service"


@pytest.mark.asyncio
async def test_mock_explains_denied_key_rotation() -> None:
    provider = MockLLMProvider()
    messages = [{"role": "user", "content": "Rotate the API key for payments-api."}]

    proposal = await provider.complete(messages, TOOLS)
    messages.extend(
        [
            proposal.assistant_message,
            {
                "role": "tool",
                "tool_call_id": proposal.tool_calls[0].id,
                "name": "rotate_api_key",
                "content": json.dumps({"denied": True, "reason": "high risk"}),
            },
        ]
    )

    final = await provider.complete(messages, TOOLS)

    assert final.tool_calls == ()
    assert "密钥" in (final.text or "")


@pytest.mark.asyncio
async def test_mock_understands_chinese_demo_requests() -> None:
    provider = MockLLMProvider()

    restore = await provider.complete(
        [{"role": "user", "content": "检查 payments-api 并安全恢复，不要轮换凭据。"}],
        TOOLS,
    )
    rotate = await provider.complete(
        [{"role": "user", "content": "请轮换 payments-api 的 API 密钥。"}],
        TOOLS,
    )

    assert restore.tool_calls[0].name == "get_service_health"
    assert rotate.tool_calls[0].name == "rotate_api_key"
