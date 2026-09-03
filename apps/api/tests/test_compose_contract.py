import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")


def test_compose_contains_the_complete_local_topology() -> None:
    for service in ("postgres:", "migrate:", "api:", "scheduler:", "control-worker:", "web:"):
        assert f"  {service}" in COMPOSE


def test_runtime_services_wait_for_successful_one_shot_migration() -> None:
    assert "migrate:" in COMPOSE
    assert "upgrade_to_head" in COMPOSE
    for service in ("api:", "scheduler:", "control-worker:"):
        lines = COMPOSE.split(f"  {service}", 1)[1].splitlines()[1:]
        block_lines = []
        for line in lines:
            if line.startswith("  ") and not line.startswith("    "):
                break
            block_lines.append(line)
        block = "\n".join(block_lines)
        assert "migrate:" in block
        assert "service_completed_successfully" in block


def test_postgres_has_no_published_host_port() -> None:
    postgres_block = COMPOSE.split("  api:", 1)[0]
    assert "ports:" not in postgres_block


def test_api_and_web_bind_only_to_loopback() -> None:
    assert '"127.0.0.1:${AGENTGATE_API_PORT:-8000}:8000"' in COMPOSE
    assert '"127.0.0.1:${AGENTGATE_WEB_PORT:-5173}:80"' in COMPOSE


def test_alternate_ports_render_consistently_through_compose() -> None:
    env = os.environ.copy()
    env.pop("AGENTGATE_API_BASE_URL", None)
    env.update({"AGENTGATE_API_PORT": "18000", "AGENTGATE_WEB_PORT": "15173"})
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    api = config["services"]["api"]
    web = config["services"]["web"]
    assert api["ports"] == [
        {
            "mode": "ingress",
            "target": 8000,
            "published": "18000",
            "protocol": "tcp",
            "host_ip": "127.0.0.1",
        }
    ]
    assert web["ports"] == [
        {
            "mode": "ingress",
            "target": 80,
            "published": "15173",
            "protocol": "tcp",
            "host_ip": "127.0.0.1",
        }
    ]
    assert api["environment"]["AGENTGATE_WEB_PORT"] == "15173"
    assert web["environment"]["AGENTGATE_API_BASE_URL"] == ""


def test_local_scripts_derive_configured_host_ports() -> None:
    start_script = (REPO_ROOT / "scripts/start-local.ps1").read_text(encoding="utf-8")
    setup_script = (REPO_ROOT / "scripts/setup-local.ps1").read_text(encoding="utf-8")
    verify_script = (REPO_ROOT / "scripts/verify-foundation.ps1").read_text(encoding="utf-8")
    for script in (start_script, setup_script, verify_script):
        assert "docker compose config --format json" in script
        assert "AGENTGATE_API_PORT" in script
        assert "AGENTGATE_WEB_PORT" in script
    assert '"http://127.0.0.1:8000/health"' not in start_script
    assert '"http://localhost:5173"' not in setup_script


def test_foundation_verification_uses_worker_environment_with_worker_dependencies() -> None:
    script = (REPO_ROOT / "scripts/verify-foundation.ps1").read_text(encoding="utf-8")
    assert 'Join-Path $repoRoot "apps\\worker"' in script
    assert 'Join-Path $workerVenv "Scripts\\python.exe"' in script
    assert "apps\\api\\.venv\\Scripts\\python.exe" not in script
    assert "win32crypt" in script
    setup_script = (REPO_ROOT / "scripts/setup-local.ps1").read_text(encoding="utf-8")
    assert "pip install -e" in setup_script


def test_scheduler_and_worker_have_distinct_durable_roles() -> None:
    assert "due-task" in COMPOSE or "due_task" in COMPOSE or "scheduler" in COMPOSE
    assert "lease" in COMPOSE
    assert "app.processes.control_worker" in COMPOSE
    assert "app.processes.scheduler" in COMPOSE
    assert "AGENTGATE_WORKER_ROLE: durable-control-task-processor" in COMPOSE


def test_local_scripts_run_migrations_before_services_and_use_npm_cmd() -> None:
    start_script = (REPO_ROOT / "scripts/start-local.ps1").read_text(encoding="utf-8")
    assert "migrate-local.ps1" in start_script
    assert "npm.cmd" in start_script
    assert start_script.index("migrate-local.ps1") < start_script.index("docker compose up -d --build api")
    assert "docker compose up -d --build api scheduler control-worker web" in start_script
    migrate_script = (REPO_ROOT / "scripts/migrate-local.ps1").read_text(encoding="utf-8")
    assert "docker compose run --rm --build migrate" in migrate_script
    assert "docker compose run --rm api" not in migrate_script
    verify_script = (REPO_ROOT / "scripts/verify-foundation.ps1").read_text(encoding="utf-8")
    assert "database_migration_current" in verify_script


def test_foundation_verification_starts_worker_before_heartbeat_gate() -> None:
    verify_script = (REPO_ROOT / "scripts/verify-foundation.ps1").read_text(encoding="utf-8")
    assert verify_script.index("-EnrollmentToken") < verify_script.index(
        "/api/platform/self-check"
    )
    assert "-StateDir" in verify_script
    assert "Remove-Item" in verify_script


def test_start_worker_uses_worker_venv_and_configured_loopback_api() -> None:
    script = (REPO_ROOT / "scripts/start-worker.ps1").read_text(encoding="utf-8")
    assert 'Join-Path $PSScriptRoot "..\\apps\\worker"' in script
    assert 'Join-Path $workerRoot ".venv\\Scripts\\python.exe"' in script
    assert 'apps\\api\\.venv\\Scripts\\python.exe' not in script
    assert "AGENTGATE_API_PORT" in script
    assert "127.0.0.1:$ApiPort" in script
    assert "localhost" in script
    assert "remote" in script.lower()
    assert "docker compose config --format json" in script
    assert "import win32crypt" in script


def test_start_worker_explicit_api_url_is_parsed_before_port_fallback() -> None:
    script = (REPO_ROOT / "scripts/start-worker.ps1").read_text(encoding="utf-8")
    assert "$parsedApiUrl" in script
    assert script.index("$parsedApiUrl") < script.index("$ApiPort = [int]$apiBindings[0].published")
    assert "parsedApiUrl.Port" in script
    assert '@("http", "https")' in script


def test_foundation_verification_delegates_worker_start_to_safe_script() -> None:
    script = (REPO_ROOT / "scripts/verify-foundation.ps1").read_text(encoding="utf-8")
    assert 'scripts\\start-worker.ps1' in script
    assert "agentgate_worker.main" not in script


def test_built_web_uses_runtime_config_without_stale_port_fallback() -> None:
    dockerfile = (REPO_ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    client = (REPO_ROOT / "apps/web/src/api/client.ts").read_text(encoding="utf-8")
    template = (REPO_ROOT / "apps/web/config.js.template").read_text(encoding="utf-8")
    assert "ARG VITE_API_BASE_URL=" in dockerfile
    assert "localhost:8000" not in dockerfile
    assert '?? "http://localhost:8000"' not in client
    assert "AGENTGATE_API_BASE_URL" in template


def test_web_entrypoint_normalizes_windows_line_endings() -> None:
    dockerfile = (REPO_ROOT / "apps/web/Dockerfile").read_text(encoding="utf-8")
    assert "sed -i 's/\\r$//' /docker-entrypoint.d/40-agentgate-config.sh" in dockerfile


def test_background_services_disable_the_api_http_healthcheck() -> None:
    for service in ("scheduler:", "control-worker:"):
        lines = COMPOSE.split(f"  {service}", 1)[1].splitlines()[1:]
        block_lines = []
        for line in lines:
            if line.startswith("  ") and not line.startswith("    "):
                break
            block_lines.append(line)
        block = "\n".join(block_lines)
        assert "healthcheck:" in block
        assert "disable: true" in block


def test_required_task7_operator_scripts_exist() -> None:
    for name in (
        "migrate-local.ps1",
        "setup-local.ps1",
        "verify-foundation.ps1",
    ):
        assert (REPO_ROOT / "scripts" / name).is_file()
