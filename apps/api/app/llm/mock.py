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
        rotation_request = (
            ("rotate" in request and "key" in request)
            or (
                any(term in request for term in ("轮换", "更换"))
                and any(term in request for term in ("密钥", "凭据", "秘钥"))
                and not any(
                    term in request
                    for term in ("不要轮换", "不轮换", "无需轮换", "不要更换", "不更换")
                )
            )
        )
        if rotation_request:
            if self._tool_results(messages, "rotate_api_key"):
                return self._final(
                    "由于这是高风险操作且未获批准，我没有执行 rotate API key（轮换 API 密钥）。"
                )
            return self._propose(messages, "rotate_api_key", {"service": "payments-api"})

        if "malformed" in request or "参数错误" in request or "错误参数" in request:
            if self._tool_results(messages, "get_service_health"):
                return self._final(
                    "工具参数有误，已拒绝且没有产生副作用。"
                )
            return self._propose(messages, "get_service_health", {"service": "unknown-api"})

        health_results = self._tool_results(messages, "get_service_health")
        if not health_results:
            service = "orders-api" if "orders" in request or "订单" in request else "payments-api"
            return self._propose(messages, "get_service_health", {"service": service})

        latest_health = self._decode(health_results[-1])
        if latest_health.get("health") == "healthy":
            return self._final("服务运行正常，无需进一步操作。")
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
                        "reason": "安全恢复已降级的 payments 服务",
                    },
                )
            latest_restart = self._decode(restart_results[-1])
            if latest_restart.get("health") == "healthy":
                return self._propose(
                    messages,
                    "get_service_health",
                    {"service": latest_health.get("service", "payments-api")},
                )

        return self._final("服务调查已完成。")

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
