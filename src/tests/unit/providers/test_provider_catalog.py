"""Providers come from an explicit catalog (WP-7.2 Part A)."""
from __future__ import annotations

import threading
import time

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
    assert sorted(audio._tts_providers) == ["faster-qwen3-tts", "fish-s2-pro", "omnivoice", "qwen3-tts-voicedesign"]
    assert sorted(audio._stt_providers) == ["parakeet"]


def test_a_duplicate_id_is_rejected() -> None:
    spec = catalog.specs("llm")[0]
    with pytest.raises(ValueError, match="duplicate llm provider id"):
        catalog._check_unique((spec, spec))


def test_a_spec_must_name_the_class_that_declares_its_id() -> None:
    wrong = ProviderSpec("not-cerebras", "llm", "app.providers.cerebras_provider", "CerebrasProvider", frozenset({"chat"}))
    with pytest.raises(ValueError, match="declares provider id 'cerebras'"):
        wrong.load()


@pytest.mark.parametrize("make", [ProviderRegistry, AudioProviderRegistry])
def test_concurrent_discovery_shows_every_caller_the_whole_table(monkeypatch, make) -> None:
    # 2026-10-31: two requests discovering at once each reset the audio tables while the other read them, and one
    # call found "4 TTS and 0 STT providers" and never began.
    real_specs = catalog.specs

    def slow_specs(kind):
        for spec in real_specs(kind):
            time.sleep(0.01)
            yield spec

    monkeypatch.setattr(catalog, "specs", slow_specs)
    registry = make()
    start = threading.Barrier(4)
    seen: list[tuple[list[str], ...]] = []

    def discover() -> None:
        start.wait()
        registry.discover_providers()
        if isinstance(registry, AudioProviderRegistry):
            seen.append((sorted(registry._tts_providers), sorted(registry._stt_providers)))
        else:
            seen.append((sorted(registry._providers),))

    threads = [threading.Thread(target=discover) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if make is AudioProviderRegistry:
        expected = (sorted(spec.id for spec in real_specs("tts")), sorted(spec.id for spec in real_specs("stt")))
    else:
        expected = (sorted(spec.id for spec in real_specs("llm")),)
    assert seen == [expected] * 4


def test_a_provider_that_fails_to_import_is_skipped(monkeypatch, caplog) -> None:
    broken = ProviderSpec("missing", "llm", "app.providers.does_not_exist", "Missing", frozenset({"chat"}))
    monkeypatch.setattr(catalog, "CATALOG", (*catalog.CATALOG, broken))
    registry = ProviderRegistry()

    registry.discover_providers()

    assert "missing" not in registry._providers
    assert "cerebras" in registry._providers
    assert "Error loading provider missing" in caplog.text
