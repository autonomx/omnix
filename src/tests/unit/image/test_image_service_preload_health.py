"""The image service is not ready after a failed preload (desktop roadmap R-9: the supervisor's memory check covered
the preload, never a load on the first request)."""
from __future__ import annotations

from services.image import image_service_runtime as runtime


def test_a_failed_preload_is_reported_as_not_ready(monkeypatch) -> None:
    monkeypatch.setattr(runtime, "image_model_status", lambda provider=None: {"ok": True})
    assert runtime.health()["ok"] is True
    monkeypatch.setattr(runtime, "_PRELOAD_FAILED", True)
    answer = runtime.health()
    assert answer["ok"] is False and answer["status"] == "preload_failed"
