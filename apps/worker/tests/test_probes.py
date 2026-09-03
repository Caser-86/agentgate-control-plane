import subprocess

import httpx
import pytest

from agentgate_worker.probes import (
    probe_http,
    probe_windows_service,
    validate_http_target,
    validate_windows_service_name,
)


def test_http_probe_returns_bounded_success_without_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        return httpx.Response(200, text="do not upload this body", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    result = probe_http("http://127.0.0.1:8000/health", client=client)

    assert result["status"] == "healthy"
    assert isinstance(result["latency_ms"], int)
    assert "do not upload" not in str(result)


def test_http_probe_marks_non_2xx_and_does_not_follow_redirect() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://example.com"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    result = probe_http("http://127.0.0.1:8000/redirect", client=client)

    assert result["status"] == "failed"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://example.com/health",
        "http://user:pass@127.0.0.1:8000/health",
        "http://127.0.0.1:8000/health?token=secret",
        "ftp://127.0.0.1:8000/health",
    ],
)
def test_http_probe_validates_local_only_endpoint(endpoint: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_http_target(endpoint)


def test_windows_service_probe_uses_fixed_sc_query_without_shell() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "STATE : 4 RUNNING", "")

    result = probe_windows_service("AgentGateWorker", runner=runner)

    assert result["status"] == "healthy"
    assert calls == [
        (
            ["sc.exe", "query", "AgentGateWorker"],
            {
                "capture_output": True,
                "check": False,
                "shell": False,
                "text": True,
                "timeout": 10,
            },
        )
    ]


def test_windows_service_probe_distinguishes_stopped_service() -> None:
    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "STATE : 1 STOPPED", "")

    result = probe_windows_service("AgentGateWorker", runner=runner)

    assert result["status"] == "failed"


@pytest.mark.parametrize("name", ["AgentGateWorker;whoami", "C:\\Windows\\service.exe", "bad name"])
def test_windows_service_probe_rejects_command_like_name(name: str) -> None:
    with pytest.raises(ValueError, match="service name"):
        validate_windows_service_name(name)
