import sys

import pytest

from agentgate_worker.main import main


def test_main_rejects_remote_api_url_before_enrollment_or_network(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_if_network_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call must not occur for a rejected API URL")

    monkeypatch.setattr("httpx.request", fail_if_network_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agentgate-worker",
            "--api-url",
            "http://example.com:8000",
            "--state-dir",
            str(tmp_path),
            "--enrollment-token",
            "test-enrollment-token",
        ],
    )

    with pytest.raises(ValueError, match="loopback"):
        main()
