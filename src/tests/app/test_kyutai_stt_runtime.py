from __future__ import annotations

import asyncio

import kyutai_stt_runtime as runtime


class FakeProvider:
    def __init__(self) -> None:
        self.base_url = "ws://127.0.0.1:8090"
        self.path = "/api/asr-streaming"
        self.probe_calls: list[tuple[str | None, float]] = []

    async def probe(self, *, language: str | None = None, max_age_seconds: float = 5.0) -> bool:
        self.probe_calls.append((language, max_age_seconds))
        return True

    async def health(self) -> dict[str, object]:
        return {
            "provider": "kyutai",
            "state": "closed",
            "upstream_ready": bool(self.probe_calls),
            "failures_in_window": 0,
            "attempts_in_window": len(self.probe_calls),
            "retry_after_seconds": 0.0,
            "last_ready_at": 1_000.0 if self.probe_calls else None,
            "last_error": None,
            "last_error_code": None,
            "last_error_type": None,
            "last_error_stage": None,
            "sample_rate": 24_000,
            "frame_samples": 1_920,
            "supported_languages": ["en", "fr"],
        }


def test_build_info_url_uses_http_root(monkeypatch) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(runtime, "provider", provider)

    assert runtime._moshi_build_info_url() == "http://127.0.0.1:8090/api/build_info"


def test_starting_moshi_does_not_attempt_websocket_probe(monkeypatch) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(runtime, "provider", provider)

    async def not_ready() -> tuple[bool, str | None, str | None]:
        return False, "upstream_connection_refused", "ConnectError"

    monkeypatch.setattr(runtime, "_moshi_http_ready", not_ready)

    health = asyncio.run(runtime._probed_health("en", force=True))

    assert health["ok"] is False
    assert health["http_ready"] is False
    assert health["upstream_ready"] is False
    assert health["last_error_code"] == "upstream_connection_refused"
    assert health["last_error_type"] == "ConnectError"
    assert health["last_error_stage"] == "build_info"
    assert health["state"] == "closed"
    assert provider.probe_calls == []


def test_ready_http_worker_advances_to_forced_websocket_probe(monkeypatch) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(runtime, "provider", provider)

    async def ready() -> tuple[bool, str | None, str | None]:
        return True, None, None

    monkeypatch.setattr(runtime, "_moshi_http_ready", ready)

    health = asyncio.run(runtime._probed_health("en", force=True))

    assert health["ok"] is True
    assert health["http_ready"] is True
    assert health["upstream_ready"] is True
    assert provider.probe_calls == [("en", 0.0)]
