from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CLIENT = REPO_ROOT / "examples/file-client/client.py"
README = REPO_ROOT / "examples/file-client/README.md"


def test_external_file_client_is_present_and_uses_the_public_api() -> None:
    assert CLIENT.is_file()
    source = CLIENT.read_text(encoding="utf-8")
    assert "AGENTGATE_API_URL" in source
    assert "AGENTGATE_CLIENT_TOKEN" in source
    assert "/api/v1/actions" in source
    assert "Idempotency-Key" in source
    assert "sqlite" not in source.lower()
    assert "AGENTGATE_LLM_API_KEY" not in source
    assert "print(token" not in source.lower()


def test_external_file_client_documentation_describes_real_boundaries() -> None:
    assert README.is_file()
    content = README.read_text(encoding="utf-8")
    for expected in (
        "file.inspect.v1",
        "file.quarantine.v1",
        "Idempotency-Key",
        "不会阻止",
        "pending_approval",
    ):
        assert expected in content
