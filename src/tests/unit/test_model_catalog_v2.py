"""Model catalog v2 (desktop roadmap §4.6): models, runtime packs and bundles."""
from __future__ import annotations

import copy

import pytest

from app.models import catalog
from app.models.catalog import CatalogError, parse_catalog

REVISION = "0123456789abcdef0123456789abcdef01234567"
FILE = {"sha256": "a" * 64, "size": 10}


def _raw() -> dict:
    return {
        "catalog_version": 2,
        "runtimes": {
            "torch-win": {"kind": "torch-layer", "platform": "windows-x64", "lock": "t.lock", "files": "t.json"},
            "tts-win": {"kind": "overlay", "base": "torch-win", "platform": "windows-x64", "service": "tts",
                        "lock": "tts.lock", "files": "tts.json"},
        },
        "bundles": {
            "voice-output": {"label": "Voice output", "capability": "tts", "variants": [
                {"platform": "windows-x64", "models": ["tts-model"], "runtimes": ["tts-win"]}]},
        },
        "models": {
            "tts-model": {"repo": "org/tts", "revision": REVISION, "service": "tts", "aliases": ["old-tts"],
                          "files": {"model.safetensors": FILE}, "licence": {"id": "Apache-2.0", "url": "https://x"}},
            "package-model": {"repo": "org/pkg", "revision": "main", "service": "audio", "source": "package",
                              "files": {}},
        },
    }


def test_the_shipped_catalog_loads_and_every_bundle_is_installable() -> None:
    shipped = catalog.load()
    assert shipped.version == 2
    assert {"voice-input", "voice-output", "transcription", "image-generation"} <= set(shipped.bundles)
    for bundle in shipped.bundles.values():
        for variant in bundle.variants:
            assert variant.models and variant.runtimes
            for model_id in variant.models:
                entry = shipped.model(model_id)
                assert entry.pinned and entry.licence.id and entry.licence.url
            for pack in shipped.runtime_closure(variant.runtimes):
                assert pack.platform == variant.platform


def test_live_voice_input_on_windows_installs_both_stt_models() -> None:
    # Nemotron gives the transcript and the EOU model the end of the utterance (nemotron_eou_streaming.py).
    variant = catalog.load().bundle("voice-input").variant("windows-x64")
    assert variant is not None
    assert set(variant.models) == {"nemotron-speech-streaming-en-0.6b", "parakeet-realtime-eou-120m-v1"}


def test_macos_voice_input_uses_parakeet_mlx_without_torch() -> None:
    shipped = catalog.load()
    variant = shipped.bundle("voice-input").variant("macos-arm64")
    assert variant is not None and variant.models == ("parakeet-tdt-0.6b-v3-mlx",)
    assert [pack.kind for pack in shipped.runtime_closure(variant.runtimes)] == ["standalone"]


def test_runtime_closure_puts_the_torch_layer_first() -> None:
    parsed = parse_catalog(_raw())
    assert [pack.id for pack in parsed.runtime_closure(["tts-win"])] == ["torch-win", "tts-win"]
    assert parsed.dependents("torch-win") == ["tts-win"]
    assert parsed.runtimes_for_model("old-tts", "windows-x64") == ["tts-win"]
    assert parsed.runtimes_for_model("tts-model", "macos-arm64") == []


def test_aliases_find_the_model() -> None:
    parsed = parse_catalog(_raw())
    assert parsed.model("old-tts").id == "tts-model"
    with pytest.raises(KeyError):
        parsed.model("missing")


def test_package_models_load_but_are_not_pinned() -> None:
    parsed = parse_catalog(_raw())
    assert not parsed.model("package-model").pinned
    raw = _raw()
    raw["bundles"]["voice-output"]["variants"][0]["models"] = ["package-model"]
    with pytest.raises(CatalogError, match="no pinned files"):
        parse_catalog(raw)


@pytest.mark.parametrize(("change", "message"), [
    (lambda raw: raw["runtimes"]["tts-win"].pop("base"), "needs a base"),
    (lambda raw: raw["runtimes"]["tts-win"].update(base="missing"), "unknown base"),
    (lambda raw: raw["runtimes"]["tts-win"].update(platform="macos-arm64"), "Torch layer for macos-arm64"),
    (lambda raw: raw["bundles"]["voice-output"]["variants"][0].update(models=["missing"]), "unknown model"),
    (lambda raw: raw["bundles"]["voice-output"]["variants"][0].update(runtimes=["missing"]), "unknown runtime"),
    (lambda raw: raw["models"]["tts-model"].update(revision="main"), "full commit hash"),
    (lambda raw: raw["models"]["tts-model"].update(files={}), "no files"),
    (lambda raw: raw["models"]["package-model"].update(aliases=["old-tts"]), "names both"),
    (lambda raw: raw["runtimes"]["tts-win"].update(kind="venv"), "kind must be"),
])
def test_malformed_catalogs_are_refused(change, message) -> None:
    raw = copy.deepcopy(_raw())
    change(raw)
    with pytest.raises(CatalogError, match=message):
        parse_catalog(raw)


def test_a_version_1_catalog_still_loads() -> None:
    parsed = parse_catalog({"models": {"m": {"repo": "org/m", "revision": REVISION, "service": "stt",
                                             "files": {"a.nemo": FILE}}}})
    assert parsed.version == 1 and parsed.model("m").label == "m" and not parsed.bundles
