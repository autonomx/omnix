"""Providers come from an explicit catalog (WP-7.2 Part A)."""
from __future__ import annotations

import pytest

from app.providers import catalog
from app.providers.audio_registry import AudioProviderRegistry
from app.providers.catalog import ProviderSpec
from app.providers.registry import ProviderRegistry


def test_registries_hold_exactly_the_catalog() -> None:
    llm = ProviderRegistry()
    llm.discover_providers()
    audio = AudioProviderRegistry()
    audio.discover_providers()

    assert sorted(llm._providers) == sorted(spec.id for spec in catalog.specs("llm"))
    assert sorted(audio._tts_providers) == ["faster-qwen3-tts"]
    assert sorted(audio._stt_providers) == ["parakeet"]


def test_a_duplicate_id_is_rejected() -> None:
    spec = catalog.specs("llm")[0]
    with pytest.raises(ValueError, match="duplicate llm provider id"):
        catalog._check_unique((spec, spec))


def test_a_spec_must_name_the_class_that_declares_its_id() -> None:
    wrong = ProviderSpec("not-cerebras", "llm", "app.providers.cerebras_provider", "CerebrasProvider", frozenset({"chat"}))
    with pytest.raises(ValueError, match="declares provider id 'cerebras'"):
        wrong.load()


def test_a_provider_that_fails_to_import_is_skipped(monkeypatch, capsys) -> None:
    broken = ProviderSpec("missing", "llm", "app.providers.does_not_exist", "Missing", frozenset({"chat"}))
    monkeypatch.setattr(catalog, "CATALOG", (*catalog.CATALOG, broken))
    registry = ProviderRegistry()

    registry.discover_providers()

    assert "missing" not in registry._providers
    assert "cerebras" in registry._providers
    assert "Error loading provider missing" in capsys.readouterr().out
