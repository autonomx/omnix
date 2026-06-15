from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.platform.settings import get_settings_payload, save_settings_payload


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _isolate_settings_files(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    import app.shared as shared

    settings_file = tmp_path / "settings.json"
    secrets_file = tmp_path / "secrets.json"
    monkeypatch.setattr(shared, "SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(shared, "SECRETS_FILE", str(secrets_file))
    shared.invalidate_provider_cache()
    return settings_file, secrets_file


def _base_settings() -> dict[str, Any]:
    return {
        "provider": "openrouter",
        "global_system_prompt": "baseline prompt",
        "lmstudio": {"base_url": "http://localhost:1234", "direct": False},
        "openrouter": {"model": "openai/gpt-4o-mini", "context_size": 128000, "thinking_budget": 0},
        "cerebras": {"model": "llama-3.3-70b-versatile"},
        "llamacpp": {"base_url": "http://localhost:8080", "model": "", "download_location": "server"},
        "audio_provider_tts": "faster-qwen3-tts",
        "audio_provider_stt": "parakeet",
        "parakeet": {"base_url": "http://localhost:8000"},
        "image": {"enabled": False, "mock": {"enabled": True}, "flux_klein": {}},
        "rpg_visual": {"enabled": False, "provider": "mock", "flux_klein": {}},
    }


def test_masked_provider_key_round_trip_preserves_secret_file(tmp_path, monkeypatch) -> None:
    settings_file, secrets_file = _isolate_settings_files(tmp_path, monkeypatch)
    _write_json(settings_file, _base_settings())
    _write_json(secrets_file, {"api_keys": {"openrouter": "or-secret-1234", "cerebras": "cb-secret-5678"}})

    payload = get_settings_payload()

    assert payload.settings["openrouter"]["api_key"] == "***1234"
    save_settings_payload({"openrouter": payload.settings["openrouter"]})

    assert _read_json(secrets_file)["api_keys"]["openrouter"] == "or-secret-1234"
    assert "api_key" not in _read_json(settings_file)["openrouter"]


def test_new_provider_key_updates_secrets_and_invalidates_provider_cache(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    settings_file, secrets_file = _isolate_settings_files(tmp_path, monkeypatch)
    _write_json(settings_file, _base_settings())
    _write_json(secrets_file, {"api_keys": {"openrouter": "or-secret-1234"}})
    shared._PROVIDER_CACHE["key"] = "cached-provider"
    shared._PROVIDER_CACHE["instance"] = object()

    save_settings_payload({"openrouter": {"api_key": "or-secret-5678", "model": "anthropic/claude-sonnet"}})

    assert _read_json(secrets_file)["api_keys"]["openrouter"] == "or-secret-5678"
    assert "api_key" not in _read_json(settings_file)["openrouter"]
    assert shared._PROVIDER_CACHE == {"key": None, "instance": None}
    assert get_settings_payload().settings["openrouter"]["api_key"] == "***5678"


def test_non_provider_settings_do_not_invalidate_provider_cache(tmp_path, monkeypatch) -> None:
    import app.shared as shared

    settings_file, secrets_file = _isolate_settings_files(tmp_path, monkeypatch)
    _write_json(settings_file, _base_settings())
    _write_json(secrets_file, {"api_keys": {"openrouter": "or-secret-1234"}})
    cached_instance = object()
    shared._PROVIDER_CACHE["key"] = "cached-provider"
    shared._PROVIDER_CACHE["instance"] = cached_instance

    save_settings_payload({"global_system_prompt": "updated prompt"})

    assert _read_json(settings_file)["global_system_prompt"] == "updated prompt"
    assert _read_json(secrets_file)["api_keys"]["openrouter"] == "or-secret-1234"
    assert shared._PROVIDER_CACHE == {"key": "cached-provider", "instance": cached_instance}
