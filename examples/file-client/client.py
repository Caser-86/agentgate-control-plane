"""AgentGate 文件动作的最小外部客户端。

该示例只调用公开的 /api/v1/actions 接口，不读取 AgentGate 数据库，也不直接访问
工作区文件。令牌和工作区 ID 通过环境变量提供，命令输出不会打印令牌。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ClientConfig:
    api_url: str
    client_token: str
    workspace_id: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls, workspace_id: str | None = None) -> ClientConfig:
        api_url = os.environ.get("AGENTGATE_API_URL", "http://127.0.0.1:8000").rstrip("/")
        parsed_url = urlparse(api_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or parsed_url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.path not in {"", "/"}
        ):
            raise ValueError("AGENTGATE_API_URL 必须是本机回环 HTTP(S) 地址")
        token = os.environ.get("AGENTGATE_CLIENT_TOKEN", "")
        resolved_workspace_id = workspace_id or os.environ.get("AGENTGATE_WORKSPACE_ID", "")
        if not token:
            raise ValueError("缺少 AGENTGATE_CLIENT_TOKEN，请从本机安全位置读取客户端令牌")
        if not resolved_workspace_id:
            raise ValueError("缺少 AGENTGATE_WORKSPACE_ID，请填写已登记的工作区 ID")
        try:
            timeout = float(os.environ.get("AGENTGATE_CLIENT_TIMEOUT", "10"))
        except ValueError as error:
            raise ValueError("AGENTGATE_CLIENT_TIMEOUT 必须是数字") from error
        if not 1 <= timeout <= 60:
            raise ValueError("AGENTGATE_CLIENT_TIMEOUT 必须在 1 到 60 秒之间")
        return cls(api_url, token, resolved_workspace_id, timeout)


class AgentGateError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class AgentGateClient:
    def __init__(self, config: ClientConfig) -> None:
        self.config = config

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.client_token}",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = Request(
            f"{self.config.api_url}{path}", data=body, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(1_048_576)
        except HTTPError as error:
            raw = error.read(16_384)
            detail = _decode_json(raw).get("error", {})
            code = str(detail.get("code", "http_error"))
            message = str(detail.get("message", "请求失败，请查看控制台中的详细状态"))
            raise AgentGateError(code, message, error.code) from error
        except (TimeoutError, URLError) as error:
            raise AgentGateError(
                "network_error", "无法连接 AgentGate API，请确认服务正在运行"
            ) from error
        result = _decode_json(raw)
        if not isinstance(result, dict):
            raise AgentGateError("invalid_response", "AgentGate 返回了无法识别的响应")
        return result

    def propose(
        self,
        action: str,
        *,
        relative_path: str | None = None,
        quarantine_entry_id: str | None = None,
        reason: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, object] = {
            "action": action,
            "workspace_id": self.config.workspace_id,
        }
        if relative_path is not None:
            payload["relative_path"] = relative_path
        if quarantine_entry_id is not None:
            payload["quarantine_entry_id"] = quarantine_entry_id
        if reason:
            payload["reason"] = reason
        return self._request("POST", "/api/v1/actions", payload, idempotency_key)

    def status(self, action_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/actions/{quote(action_id, safe='')}")


def _decode_json(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通过 AgentGate 请求受控文件动作")
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTGATE_WORKSPACE_ID"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, action, help_text in (
        ("inspect", "file.inspect.v1", "只读检查文件"),
        ("quarantine", "file.quarantine.v1", "申请隔离普通文件"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.set_defaults(action=action)
        command.add_argument("--path", required=True, help="工作区内的相对路径")
        command.add_argument("--idempotency-key", required=True)
        if name == "quarantine":
            command.add_argument("--reason", default=None)
    restore = subparsers.add_parser("restore", help="申请恢复隔离文件")
    restore.set_defaults(action="file.restore.v1")
    restore.add_argument("--quarantine-entry-id", required=True)
    restore.add_argument("--idempotency-key", required=True)
    status = subparsers.add_parser("status", help="查询已有动作状态")
    status.add_argument("--action-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    options = _parser().parse_args(argv)
    try:
        config = ClientConfig.from_environment(options.workspace_id)
        client = AgentGateClient(config)
        if options.command == "status":
            result = client.status(options.action_id)
        elif options.command == "restore":
            result = client.propose(
                options.action,
                quarantine_entry_id=options.quarantine_entry_id,
                idempotency_key=options.idempotency_key,
            )
        else:
            result = client.propose(
                options.action,
                relative_path=options.path,
                reason=getattr(options, "reason", None),
                idempotency_key=options.idempotency_key,
            )
    except (AgentGateError, ValueError) as error:
        code = error.code if isinstance(error, AgentGateError) else "client_config_error"
        print(f"错误[{code}] {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
