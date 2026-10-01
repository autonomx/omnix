import pytest

from app.providers import tts_abstraction


def test_tts_provider_registry_expires_and_is_invalidatable(monkeypatch) -> None:
    tts_abstraction.clear_tts_provider_registrations()
    now = {"value": 10.0}
    provider = object()
    monkeypatch.setattr(tts_abstraction.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(tts_abstraction, "TTS_PROVIDER_REGISTRATION_TTL_SECONDS", 5.0)

    tts_abstraction.register_provider("temporary", provider)
    assert tts_abstraction.get_provider("temporary") is provider
    now["value"] = 16.0
    assert tts_abstraction.get_provider("temporary") is None
    assert tts_abstraction.list_providers() == []

    tts_abstraction.register_provider("clear-me", provider)
    tts_abstraction.clear_tts_provider_registrations()
    assert tts_abstraction.get_provider("clear-me") is None


def test_tts_provider_registry_rejects_new_entries_at_capacity(monkeypatch) -> None:
    tts_abstraction.clear_tts_provider_registrations()
    monkeypatch.setattr(tts_abstraction, "MAX_TTS_PROVIDER_REGISTRATIONS", 1)
    tts_abstraction.register_provider("first", object())

    with pytest.raises(ValueError, match="capacity"):
        tts_abstraction.register_provider("second", object())

    tts_abstraction.clear_tts_provider_registrations()
