from __future__ import annotations

from pathlib import Path

from app.launcher.kyutai_services import build_kyutai_service_specs
from app.launcher.runtime_control_app import build_runtime_service_specs


def test_kyutai_launcher_specs_auto_start_for_branch_testing(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_KYUTAI_ENABLED", raising=False)
    monkeypatch.delenv("OMNIX_START_KYUTAI_MOSHI", raising=False)
    monkeypatch.delenv("OMNIX_START_KYUTAI_ADAPTER", raising=False)
    monkeypatch.delenv("KYUTAI_STT_PATH", raising=False)
    monkeypatch.delenv("VITE_ASSISTANT_STT_URL", raising=False)
    monkeypatch.setenv("RPG_FLUX_PYTHON", "F:/Python/python.exe")

    root = Path("F:/LLM/omnix")
    specs, browser_url = build_kyutai_service_specs(root)
    by_id = {spec.service_id: spec for spec in specs}

    assert set(by_id) == {"kyutai_moshi", "kyutai_stt"}
    assert by_id["kyutai_moshi"].enabled is True
    assert by_id["kyutai_moshi"].auto_start is True
    assert by_id["kyutai_moshi"].optional is True
    assert by_id["kyutai_moshi"].command == [
        "F:/Python/python.exe",
        str(root / "scripts" / "run_kyutai_moshi.py"),
    ]
    assert "127.0.0.1:8090" in by_id["kyutai_moshi"].description

    adapter = by_id["kyutai_stt"]
    assert adapter.enabled is True
    assert adapter.auto_start is True
    assert adapter.optional is True
    assert adapter.ports == (5202,)
    assert adapter.env["KYUTAI_STT_URL"] == "ws://127.0.0.1:8090"
    assert adapter.env["KYUTAI_STT_PATH"] == "/api/asr-streaming"
    assert adapter.env["OMNIX_STT_PORT"] == "5202"
    assert "127.0.0.1:8090/api/asr-streaming" in adapter.description
    assert browser_url == (
        "http://127.0.0.1:5202?language=en&authority=test"
        "&endpoint_threshold=0.75"
        "&fallback=http%3A%2F%2F127.0.0.1%3A5201"
    )


def test_kyutai_launcher_services_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_KYUTAI_ENABLED", "0")

    specs, _browser_url = build_kyutai_service_specs(Path("F:/LLM/omnix"))

    assert all(spec.optional for spec in specs)
    assert all(not spec.enabled for spec in specs)
    assert all(not spec.auto_start for spec in specs)


def test_runtime_dashboard_inserts_kyutai_before_gateway_and_configures_web(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OMNIX_KYUTAI_ENABLED", "1")
    monkeypatch.setenv("OMNIX_START_KYUTAI_MOSHI", "1")
    monkeypatch.setenv("OMNIX_START_KYUTAI_ADAPTER", "1")
    monkeypatch.delenv("VITE_ASSISTANT_STT_URL", raising=False)
    monkeypatch.delenv("OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES", raising=False)
    monkeypatch.delenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", raising=False)

    specs = build_runtime_service_specs()
    ids = [spec.service_id for spec in specs]
    by_id = {spec.service_id: spec for spec in specs}

    assert ids.index("kyutai_moshi") < ids.index("kyutai_stt")
    assert ids.index("kyutai_stt") < ids.index("gateway")
    assert by_id["kyutai_moshi"].auto_start is True
    assert by_id["kyutai_stt"].auto_start is True
    assert by_id["kyutai_stt"].env["KYUTAI_STT_PATH"] == "/api/asr-streaming"
    assert by_id["gateway"].env["OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"] == "true"
    assert by_id["gateway"].env["OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS"] == "2"
    assert by_id["web"].env["VITE_ASSISTANT_STT_URL"].startswith(
        "http://127.0.0.1:5202?"
    )
    assert "authority=test" in by_id["web"].env["VITE_ASSISTANT_STT_URL"]
    assert by_id["web"].env["VITE_LIVE_SPECULATION_ENABLED"] == "true"
    assert by_id["web"].env["VITE_LIVE_TTS_ADAPTIVE_BUFFER"] == "true"


def test_runtime_dashboard_allows_stateful_response_opt_out(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_KYUTAI_ENABLED", "1")
    monkeypatch.setenv("OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES", "false")
    monkeypatch.setenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", "4")

    by_id = {spec.service_id: spec for spec in build_runtime_service_specs()}

    assert by_id["gateway"].env["OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"] == "false"
    assert by_id["gateway"].env["OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS"] == "4"
