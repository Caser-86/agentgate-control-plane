import pytest
from pydantic import ValidationError

from app.tools.registry import ToolRegistry, UnknownToolError


def test_registry_exposes_only_allowlisted_tools() -> None:
    registry = ToolRegistry()

    assert [tool.spec.name for tool in registry.registered()] == [
        "get_service_health",
        "search_logs",
        "restart_service",
        "rotate_api_key",
        "platform.self_check",
    ]


def test_registry_emits_openai_function_schemas() -> None:
    schemas = ToolRegistry().schemas()

    assert len(schemas) == 5
    assert all(item["type"] == "function" for item in schemas)
    assert {item["function"]["name"] for item in schemas} == {
        "get_service_health",
        "search_logs",
        "restart_service",
        "rotate_api_key",
        "platform.self_check",
    }


def test_unknown_names_raise_unknown_tool_error() -> None:
    with pytest.raises(UnknownToolError):
        ToolRegistry().get("run_shell")


def test_invalid_arguments_fail_before_handler_invocation() -> None:
    registry = ToolRegistry()

    with pytest.raises(ValidationError):
        registry.validate("restart_service", {"service": "payments-api", "reason": "no"})


def test_rotate_api_key_has_no_executable_handler() -> None:
    assert ToolRegistry().get("rotate_api_key").handler is None
