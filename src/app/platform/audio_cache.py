"""Configuration-sensitive invalidation for legacy singleton audio providers."""
from __future__ import annotations

import json
from typing import Any


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fingerprint(settings: dict[str, Any], kind: str) -> str:
    provider_key = "audio_provider_tts" if kind == "tts" else "audio_provider_stt"
    default_provider = "faster-qwen3-tts" if kind == "tts" else "parakeet"
    provider = str(settings.get(provider_key) or default_provider)
    payload = {
        "provider": provider,
        "config": _record(settings.get(provider)),
        "worker_url": settings.get(f"{kind}_worker_url"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _stop(instance: Any) -> None:
    if instance is None or not hasattr(instance, "stop"):
        return
    try:
        instance.stop()
    except Exception:
        pass


def invalidate_changed_audio_caches(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, bool]:
    """Clear cached providers whose effective configuration changed."""

    from app import shared

    tts_changed = _fingerprint(before, "tts") != _fingerprint(after, "tts")
    stt_changed = _fingerprint(before, "stt") != _fingerprint(after, "stt")

    if tts_changed:
        _stop(getattr(shared, "_tts_provider_instance", None))
        shared._tts_provider_instance = None
        shared._tts_provider_name = None
    if stt_changed:
        _stop(getattr(shared, "_stt_provider_instance", None))
        shared._stt_provider_instance = None
        shared._stt_provider_name = None
    return tts_changed, stt_changed
