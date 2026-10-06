"""llama.cpp server lifecycle: explicit auto-start, drained output, readiness (WP-8.4)."""
import socket
import subprocess
import sys

import pytest

from app.providers import llamacpp_provider
from app.providers.base import ConnectionError as ProviderConnectionError, ProviderConfig
from app.providers.llamacpp_provider import LlamaCppProvider


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def provider(tmp_path, monkeypatch):
    def make(*, auto_start: bool, server_script: str | None = None) -> LlamaCppProvider:
        provider = LlamaCppProvider(ProviderConfig(
            provider_type="llamacpp", base_url=f"http://127.0.0.1:{_free_port()}",
            extra_params={"model_dir": str(tmp_path), "auto_start": auto_start},
        ))
        monkeypatch.setattr(provider, "_find_server_binary", lambda: tmp_path / "llama-server")
        monkeypatch.setattr(llamacpp_provider, "bind_host", lambda: "127.0.0.1")
        monkeypatch.setattr(provider, "_is_server_running", lambda: False)
        real_popen = subprocess.Popen

        def popen(_command, **kwargs):
            if server_script is None:
                pytest.fail("the server was started")
            kwargs.pop("cwd", None)
            return real_popen([sys.executable, "-c", server_script], **kwargs)

        monkeypatch.setattr(llamacpp_provider.subprocess, "Popen", popen)
        return provider

    return make


def test_a_stopped_server_is_not_started_without_auto_start(provider, tmp_path):
    with pytest.raises(ProviderConnectionError, match="not running .* enable auto_start"):
        provider(auto_start=False)._ensure_server(tmp_path / "model.gguf")


def test_server_output_is_drained_so_a_chatty_server_never_blocks(provider, tmp_path):
    # ~1.6 MB of logs: far more than a pipe buffer holds.
    chatty = provider(auto_start=True, server_script="for i in range(20000): print('x' * 79, i)")

    chatty._start_server(str(tmp_path / "model.gguf"))
    process = chatty._server_process

    assert process.wait(timeout=60) == 0  # it would block forever on an unread pipe
    chatty._server_log_reader.join(timeout=10)
    tail = chatty.server_log_tail()
    assert len(tail) == chatty.LOG_TAIL_LINES
    assert tail[-1] == "x" * 79 + " 19999"


def test_a_server_that_exits_during_startup_reports_its_last_words(provider, tmp_path):
    failing = provider(
        auto_start=True,
        server_script="import sys\nprint('error: invalid model file')\nsys.exit(3)",
    )

    with pytest.raises(ProviderConnectionError, match=r"exited during startup \(code 3\): error: invalid model file"):
        failing._ensure_server(tmp_path / "model.gguf")
    assert failing._server_process is None
