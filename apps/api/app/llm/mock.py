import hashlib
import json
from typing import Any

from app.llm.base import ModelTurn, ToolCall


class MockLLMProvider:
    provider_name = "mock"

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> ModelTurn:
        del tools
        request = self._request(messages).lower()
        if "rotate" in request and "key" in request:
            if self._tool_results(messages, "rotate_api_key"):
                return self._final(
                    "I did not rotate the API key because the high-risk action was denied."
                )
            return self._propose(messages, "rotate_api_key", {"service": "payments-api"})

        if "malformed" in request:
            if self._tool_results(messages, "get_service_health"):
                return self._final(
                    "The malformed tool arguments were rejected without side effects."
                )
            return self._propose(messages, "get_service_health", {"service": "unknown-api"})

        health_results = self._tool_results(messages, "get_service_health")
        if not health_results:
            service = "orders-api" if "orders" in request else "payments-api"
            return self._propose(messages, "get_service_health", {"service": service})

        latest_health = self._decode(health_results[-1])
        if latest_health.get("health") == "healthy":
            return self._final("The service is healthy and no further action is required.")
        if latest_health.get("health") == "degraded":
            log_results = self._tool_results(messages, "search_logs")
            if not log_results:
                return self._propose(
                    messages,
                    "search_logs",
                    {
                        "service": latest_health.get("service", "payments-api"),
                        "severity": "error",
                        "limit": 20,
                    },
                )
            restart_results = self._tool_results(messages, "restart_service")
            if not restart_results:
                return self._propose(
                    messages,
                    "restart_service",
                    {
                        "service": latest_health.get("service", "payments-api"),
                        "reason": "recover the degraded payments service safely",
                    },
                )

        return self._final("The service investigation is complete.")

    @staticmethod
    def _request(messages: list[dict[str, object]]) -> str:
        for message in messages:
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return ""

    @staticmethod
    def _tool_results(messages: list[dict[str, object]], name: str) -> list[str]:
        return [
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "tool" and message.get("name") == name
        ]

    @staticmethod
    def _decode(value: str) -> dict[str, Any]:
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @classmethod
    def _call_id(cls, messages: list[dict[str, object]], name: str) -> str:
        payload = json.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)
        digest = hashlib.sha256(f"{payload}:{name}".encode()).hexdigest()[:16]
        return f"mock_{digest}"

    @classmethod
    def _propose(
        cls, messages: list[dict[str, object]], name: str, arguments: dict[str, object]
    ) -> ModelTurn:
        call = ToolCall(cls._call_id(messages, name), name, arguments)
        return ModelTurn(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(arguments)},
                    }
                ],
            },
            None,
            (call,),
        )

    @staticmethod
    def _final(text: str) -> ModelTurn:
        return ModelTurn({"role": "assistant", "content": text}, text, ())
