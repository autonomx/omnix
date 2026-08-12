from __future__ import annotations

from app.launcher.runtime_control_app import build_runtime_service_specs


def test_runtime_dashboard_uses_hybrid_stt(monkeypatch) -> None:
    monkeypatch.delenv("VITE_ASSISTANT_STT_URL", raising=False)
    monkeypatch.delenv("OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES", raising=False)
    monkeypatch.delenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", raising=False)

    by_id = {spec.service_id: spec for spec in build_runtime_service_specs()}

    assert by_id["stt"].label == "Nemotron + Parakeet EOU STT"
    assert by_id["stt"].enabled is True
    assert by_id["stt"].auto_start is True
    assert by_id["stt"].env["OMNIX_STT_URL"] == "http://127.0.0.1:5201"
    assert by_id["stt"].command[-1].replace("\\", "/").endswith(
        "/src/nemotron_eou_stt_server.py"
    )
    assert by_id["gateway"].env["OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"] == "true"
    assert by_id["gateway"].env["OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS"] == "2"
    assert by_id["web"].env["VITE_ASSISTANT_STT_URL"].startswith(
        "http://127.0.0.1:5201?"
    )
    assert "authority=auto" in by_id["web"].env["VITE_ASSISTANT_STT_URL"]
    assert "endpoint_threshold=0.5" in by_id["web"].env["VITE_ASSISTANT_STT_URL"]
    assert by_id["web"].env["VITE_LIVE_SPECULATION_ENABLED"] == "true"
    assert by_id["web"].env["VITE_LIVE_TTS_ADAPTIVE_BUFFER"] == "true"


def test_runtime_dashboard_allows_live_voice_overrides(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES", "false")
    monkeypatch.setenv("OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS", "4")
    monkeypatch.setenv(
        "VITE_ASSISTANT_STT_URL",
        "http://127.0.0.1:5201?language=en&authority=test&endpoint_threshold=0.75",
    )

    by_id = {spec.service_id: spec for spec in build_runtime_service_specs()}

    assert by_id["gateway"].env["OMNIX_LIVE_LMSTUDIO_STATEFUL_RESPONSES"] == "false"
    assert by_id["gateway"].env["OMNIX_LIVE_TTS_SPECULATIVE_CHUNK_STEPS"] == "4"
    assert by_id["web"].env["VITE_ASSISTANT_STT_URL"].endswith(
        "authority=test&endpoint_threshold=0.75"
    )


def test_runtime_dashboard_has_no_alternate_stt_service() -> None:
    service_ids = [spec.service_id for spec in build_runtime_service_specs()]

    assert service_ids.count("stt") == 1
    assert all("moshi" not in service_id.casefold() for service_id in service_ids)
