import ipaddress
import os
import re
import subprocess
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

MAX_DETAIL_LENGTH = 512
SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
SERVICE_STATE_PATTERN = re.compile(r"STATE\s*:\s*\d+\s+([A-Z_]+)")


def _detail(value: str) -> str:
    return value.replace("\x00", " ").strip()[:MAX_DETAIL_LENGTH]


def validate_http_target(endpoint: str) -> str:
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("HTTP target must be a valid loopback URL") from error
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("HTTP target must be a valid loopback URL")
    normalized_host = hostname.lower().rstrip(".")
    is_loopback = normalized_host == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(normalized_host).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("HTTP target must target a loopback host")
    if port is not None and not 1 <= port <= 65_535:
        raise ValueError("HTTP target port must be between 1 and 65535")
    return endpoint.strip()


def validate_windows_service_name(name: str) -> str:
    if SERVICE_NAME_PATTERN.fullmatch(name.strip()) is None:
        raise ValueError("Windows service name is invalid")
    return name.strip()


def probe_http(
    endpoint: str,
    *,
    timeout_seconds: int = 5,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    normalized_endpoint = validate_http_target(endpoint)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= 30
    ):
        raise ValueError("HTTP target timeout must be between 1 and 30 seconds")
    owned_client = client is None
    active_client = client or httpx.Client(follow_redirects=False)
    started_at = time.perf_counter()
    try:
        response = active_client.get(normalized_endpoint, timeout=timeout_seconds)
        status = "healthy" if 200 <= response.status_code < 300 else "failed"
        return {
            "status": status,
            "detail": _detail(f"HTTP {response.status_code}"),
            "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
        }
    except httpx.TimeoutException:
        return {
            "status": "failed",
            "detail": "HTTP 请求超时",
            "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
        }
    except httpx.HTTPError:
        return {"status": "unknown", "detail": "HTTP 探针无法执行"}
    finally:
        if owned_client:
            active_client.close()


def probe_windows_service(
    name: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, object]:
    service_name = validate_windows_service_name(name)
    if runner is None:
        if os.name != "nt":
            return {"status": "unknown", "detail": "Windows 服务探针仅支持 Windows"}
        runner = subprocess.run
    try:
        completed = runner(
            ["sc.exe", "query", service_name],
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {"status": "unknown", "detail": "Windows 服务探针无法执行"}
    output = _detail(f"{completed.stdout}\n{completed.stderr}")
    state_match = SERVICE_STATE_PATTERN.search(output.upper())
    if completed.returncode != 0:
        return {"status": "failed", "detail": "Windows 服务查询失败"}
    if state_match is None:
        return {"status": "unknown", "detail": "Windows 服务状态未知"}
    state = state_match.group(1)
    return {
        "status": "healthy" if state == "RUNNING" else "failed",
        "detail": _detail(f"Windows 服务 {state}"),
    }
