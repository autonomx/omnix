"""Voice Studio Phase 5: OmniVoice as an engine, and the Models tool's environment and grouping facts.

OmniVoice's provider contract (synthesis, cloning, sliders, lifecycle) is in
``src/tests/unit/providers/test_tts_provider_contract.py``; selecting an engine
under the swap lease is in ``test_voice_studio_phase1_postgres.py``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.platform.voice import model_install, tts_engines
from app.platform.voice.model_catalog import speech_model


def test_omnivoice_needs_its_non_commercial_terms_accepted() -> None:
    model = speech_model("omnivoice")
    assert model.licence == "CC-BY-NC-4.0" and not model.commercial_use and model.requires_acceptance
    with pytest.raises(model_install.ModelInstallError, match="not for commercial use"):
        model_install.install_model("omnivoice", accept_terms=False, hub=object())


def test_a_model_reports_whether_its_service_environment_exists(monkeypatch, tmp_path: Path) -> None:
    from app.config.launcher import LauncherConfig

    present = tmp_path / "omnix-audio" / "python.exe"
    present.parent.mkdir()
    present.write_bytes(b"")
    config = LauncherConfig(conda_root=tmp_path, environments={"audio": "omnix-audio", "omnivoice": "omnix-omnivoice"},
                            pythons={"audio": str(present), "omnivoice": str(tmp_path / "missing" / "python.exe")})
    monkeypatch.setattr("app.config.launcher.load_launcher_config", lambda root: config)
    monkeypatch.delenv("OMNIX_OMNIVOICE_PYTHON", raising=False)
    monkeypatch.delenv("OMNIX_AUDIO_PYTHON", raising=False)
    missing = model_install.service_environment("omnivoice")
    assert missing["ready"] is False and missing["name"] == "omnix-omnivoice"
    assert missing["setup"].endswith("--require-hashes -r src/services/omnivoice/omnivoice.lock.txt")
    assert model_install.service_environment("audio")["ready"] is True
    # A service with no launcher role (none yet) never blocks an install.
    assert model_install.service_environment("unknown") == {"name": "", "ready": True, "setup": ""}


def test_engines_are_grouped_by_what_they_do_best() -> None:
    from app.providers.catalog import provider_capabilities

    groups = {engine: tts_engines.engine_group(engine, provider_capabilities(engine, "tts"))
              for engine in tts_engines.local_engine_ids()}
    assert groups == {"faster-qwen3-tts": "clone", "fish-s2-pro": "delivery", "omnivoice": "many_languages"}


def test_omnivoice_is_selectable_once_its_weights_are_installed(monkeypatch, tmp_path: Path) -> None:
    from app.providers import omnivoice_provider

    weights = tmp_path / "OmniVoice"
    monkeypatch.setattr("app.settings.access.load_settings", lambda: {"omnivoice": {"model_dir": str(weights)}})
    assert tts_engines._installed("omnivoice")[0] is False
    weights.mkdir()
    (weights / "model.safetensors").write_bytes(b"x")
    assert tts_engines._installed("omnivoice") == (True, "")
    assert omnivoice_provider.OmniVoiceTTSProvider.local_model_artifacts().directory == weights.resolve()


def test_selection_is_refused_while_a_voice_tool_holds_the_gpu(monkeypatch) -> None:
    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: True)
    monkeypatch.setattr("app.persistence.tts_swap.begin_swap", lambda *args, **kwargs: None)
    tts_engines._update(phase="idle")
    with pytest.raises(RuntimeError, match="swapped in"):
        tts_engines.select_tts_engine("omnivoice")
    assert tts_engines._SWITCH["phase"] == "idle"


def test_the_hardware_report_covers_cuda_apple_silicon_and_neither() -> None:
    from types import SimpleNamespace

    from app.providers.gpu_report import gpu_memory

    gb = 1024 ** 3
    cuda = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, mem_get_info=lambda: (20 * gb, 24 * gb),
                                                get_device_name=lambda index: "NVIDIA GeForce RTX 4090"))
    assert gpu_memory(cuda) == {"vram_free_bytes": 20 * gb, "vram_total_bytes": 24 * gb,
                                "device": "NVIDIA GeForce RTX 4090"}
    apple = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False),
                            backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)),
                            mps=SimpleNamespace(recommended_max_memory=lambda: 21 * gb,
                                                driver_allocated_memory=lambda: 5 * gb))
    assert gpu_memory(apple) == {"vram_free_bytes": 16 * gb, "vram_total_bytes": 21 * gb,
                                 "device": "Apple Silicon (MPS)", "unified_memory": True}
    neither = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False),
                              backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)))
    assert gpu_memory(neither) == {}
