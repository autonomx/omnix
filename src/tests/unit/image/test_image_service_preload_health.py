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


def test_a_load_refused_for_memory_answers_with_the_reason(monkeypatch) -> None:
    """Error bodies leave the model service as bare codes, so the refusal is an answer the image view can show."""
    import asyncio
    from types import SimpleNamespace

    from app.platform.image.lifecycle import ImageLoadBudgetError

    def refuse(provider):
        raise ImageLoadBudgetError("flux_insufficient_memory:available_gib=8.00 required_gib=22.00",
                                   "Not enough memory to load the image model: 8.0 GB free, about 22 GB needed.")

    monkeypatch.setattr(runtime, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(runtime, "_local_model_status", lambda provider: {"complete": True})
    monkeypatch.setattr(runtime, "is_image_provider_loaded", lambda provider: False)
    monkeypatch.setattr(runtime, "unload_all_image_providers", lambda: None)
    monkeypatch.setattr(runtime, "load_image_provider", refuse)
    monkeypatch.setattr(runtime, "image_model_status", lambda provider=None: {"ok": True})
    body = SimpleNamespace(model_dump=lambda **kwargs: {"provider": "flux_klein"})
    answer = asyncio.run(runtime.provider_load(None, body))
    assert answer["ok"] is False and answer["error"].startswith("Not enough memory to load the image model")
