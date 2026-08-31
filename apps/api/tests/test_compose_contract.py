from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")


def test_compose_contains_the_complete_local_topology() -> None:
    for service in ("postgres:", "api:", "scheduler:", "control-worker:", "web:"):
        assert f"  {service}" in COMPOSE


def test_postgres_has_no_published_host_port() -> None:
    postgres_block = COMPOSE.split("  api:", 1)[0]
    assert "ports:" not in postgres_block


def test_api_and_web_bind_only_to_loopback() -> None:
    assert '"127.0.0.1:${AGENTGATE_API_PORT:-8000}:8000"' in COMPOSE
    assert '"127.0.0.1:${AGENTGATE_WEB_PORT:-5173}:80"' in COMPOSE


def test_scheduler_and_worker_have_distinct_durable_roles() -> None:
    assert "due-task" in COMPOSE or "due_task" in COMPOSE or "scheduler" in COMPOSE
    assert "lease" in COMPOSE
    assert "app.processes.control_worker" in COMPOSE


def test_local_scripts_run_migrations_before_services_and_use_npm_cmd() -> None:
    start_script = (REPO_ROOT / "scripts/start-local.ps1").read_text(encoding="utf-8")
    assert "migrate-local.ps1" in start_script
    assert "npm.cmd" in start_script
    assert start_script.index("migrate-local.ps1") < start_script.index("docker compose up -d api")


def test_required_task7_operator_scripts_exist() -> None:
    for name in (
        "migrate-local.ps1",
        "setup-local.ps1",
        "verify-foundation.ps1",
    ):
        assert (REPO_ROOT / "scripts" / name).is_file()
