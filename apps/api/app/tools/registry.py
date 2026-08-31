from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel
from sqlmodel import Session

from app.models import RiskLevel
from app.tools.base import ToolSpec
from app.tools.operations import (
    RestartServiceArgs,
    SearchLogsArgs,
    ServiceArgs,
    get_service_health,
    restart_service,
    search_logs,
)

ToolHandler = Callable[[BaseModel, Session], Awaitable[dict[str, object]]]


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    arguments_model: type[BaseModel]
    handler: ToolHandler | None


class SelfCheckArgs(BaseModel):
    pass


class UnknownToolError(LookupError):
    pass


def _health_handler(args: BaseModel, session: Session) -> Awaitable[dict[str, object]]:
    return get_service_health(cast(ServiceArgs, args), session)


def _logs_handler(args: BaseModel, session: Session) -> Awaitable[dict[str, object]]:
    return search_logs(cast(SearchLogsArgs, args), session)


def _restart_handler(args: BaseModel, session: Session) -> Awaitable[dict[str, object]]:
    return restart_service(cast(RestartServiceArgs, args), session)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {
            "get_service_health": RegisteredTool(
                ToolSpec(
                    name="get_service_health",
                    description="Read the health and restart count of a local demo service.",
                    parameters_schema=ServiceArgs.model_json_schema(),
                    risk_level=RiskLevel.LOW,
                    read_only=True,
                ),
                ServiceArgs,
                _health_handler,
            ),
            "search_logs": RegisteredTool(
                ToolSpec(
                    name="search_logs",
                    description="Read deterministic diagnostic logs for a local demo service.",
                    parameters_schema=SearchLogsArgs.model_json_schema(),
                    risk_level=RiskLevel.LOW,
                    read_only=True,
                ),
                SearchLogsArgs,
                _logs_handler,
            ),
            "restart_service": RegisteredTool(
                ToolSpec(
                    name="restart_service",
                    description="Restart a local demo service and restore it to healthy.",
                    parameters_schema=RestartServiceArgs.model_json_schema(),
                    risk_level=RiskLevel.MEDIUM,
                    read_only=False,
                ),
                RestartServiceArgs,
                _restart_handler,
            ),
            "rotate_api_key": RegisteredTool(
                ToolSpec(
                    name="rotate_api_key",
                    description="Request an API key rotation; never executable in the local demo.",
                    parameters_schema=ServiceArgs.model_json_schema(),
                    risk_level=RiskLevel.HIGH,
                    read_only=False,
                ),
                ServiceArgs,
                None,
            ),
            "platform.self_check": RegisteredTool(
                ToolSpec(
                    name="platform.self_check",
                    description="Read-only native Worker protocol self-check.",
                    parameters_schema=SelfCheckArgs.model_json_schema(),
                    risk_level=RiskLevel.LOW,
                    read_only=True,
                ),
                SelfCheckArgs,
                None,
            ),
        }

    def registered(self) -> tuple[RegisteredTool, ...]:
        return tuple(self._tools.values())

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownToolError(f"unknown tool: {name}") from exc

    def validate(self, name: str, arguments: dict[str, object]) -> BaseModel:
        return self.get(name).arguments_model.model_validate(arguments)

    def schemas(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.spec.name,
                    "description": tool.spec.description,
                    "parameters": tool.spec.parameters_schema,
                },
            }
            for tool in self.registered()
        ]

    def replace(self, name: str, tool: RegisteredTool) -> None:
        self.get(name)
        self._tools[name] = tool
