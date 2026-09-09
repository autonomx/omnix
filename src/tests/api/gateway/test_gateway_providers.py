"""Contract tests for the unified provider facade."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi.testclient import TestClient


SRC_DIR = Path(__file__).resolve().parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _client() -> TestClient:
    from app.gateway.main import create_gateway_app
    from app.providers.facade import ProviderFacade

    facade = ProviderFacade(
        llm_lister=lambda: [
            {
                "name": "lmstudio",
                "display_name": "LM Studio",
                "capabilities": ["chat", "models", "embeddings"],
            }
        ],
        tts_lister=lambda: [
            {
                "name": "faster-qwen3-tts",
                "display_name": "Faster Qwen3 TTS",
                "capabilities": ["voice_cloning"],
            }
        ],
        stt_lister=lambda: [{"name": "parakeet", "display_name": "Parakeet"}],
        image_lister=lambda: [{"key": "mock", "label": "Mock Image Provider", "status": "available"}],
        visual_lister=lambda: [{"key": "disabled", "label": "Disabled"}],
        settings_loader=lambda: {
            "lmstudio": {"model": "local-chat-model"},
            "faster-qwen3-tts": {"model_name": "Qwen/Qwen3-TTS"},
        },
    )
    return TestClient(
        create_gateway_app(provider_facade_factory=lambda: facade),
        raise_server_exceptions=False,
    )


def test_gateway_provider_facade_lists_capabilities_and_models() -> None:
    client = _client()

    response = client.get("/api/providers")

    assert response.status_code == 200
    payload = response.json()
    providers = {provider["id"]: provider for provider in payload["providers"]}
    assert providers["llm:lmstudio"]["capabilities"] == [
        "chat",
        "completion",
        "diagnostics",
        "model_discovery",
        "embedding",
    ]
    assert providers["tts:faster-qwen3-tts"]["capabilities"] == [
        "tts",
        "diagnostics",
        "voice_cloning",
    ]
    assert providers["image:mock"]["capabilities"] == ["image", "diagnostics"]

    models = {model["provider_id"]: model for model in payload["models"]}
    assert models["llm:lmstudio"]["id"] == "llm:lmstudio:local-chat-model"
    assert models["llm:lmstudio"]["location"] == "local"
    assert models["tts:faster-qwen3-tts"]["id"] == "tts:faster-qwen3-tts:Qwen/Qwen3-TTS"


def test_gateway_models_endpoint_uses_same_facade_payload() -> None:
    client = _client()

    response = client.get("/api/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["models"]
    assert payload["providers"]


def test_gateway_provider_payload_is_offloaded_from_event_loop(monkeypatch) -> None:
    from app.gateway import main
    from app.providers.facade import ProviderFacade

    facade = ProviderFacade(
        llm_lister=lambda: [],
        tts_lister=lambda: [],
        stt_lister=lambda: [],
        image_lister=lambda: [],
        visual_lister=lambda: [],
        settings_loader=lambda: {},
    )
    app = main.create_gateway_app(provider_facade_factory=lambda: facade)
    route = next(route for route in app.routes if route.path == "/api/providers")
    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(main.asyncio, "to_thread", fake_to_thread)
    payload = asyncio.run(route.endpoint())

    assert payload.providers == []
    assert payload.models == []
    assert len(calls) == 1
