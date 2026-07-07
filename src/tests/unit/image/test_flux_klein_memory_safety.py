from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.image import flux_pipeline_compat
from app.image.providers import flux_klein_provider as flux_module
from app.image.providers.flux_klein_provider import FluxKleinImageProvider


def test_direct_cuda_mode_rejects_loading_when_free_vram_is_too_low(monkeypatch) -> None:
    provider = FluxKleinImageProvider(
        {
            "device": "cuda",
            "enable_cpu_offload": False,
            "min_cuda_free_gib": 14,
        }
    )
    monkeypatch.setattr(flux_module.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(flux_module, "_cuda_memory_gib", lambda: (8.0, 24.0))

    with pytest.raises(RuntimeError, match="flux_klein_insufficient_vram"):
        provider._resolve_memory_mode()


def test_explicit_cpu_offload_can_run_below_direct_cuda_threshold(monkeypatch) -> None:
    provider = FluxKleinImageProvider(
        {
            "device": "cuda",
            "enable_cpu_offload": True,
        }
    )
    monkeypatch.setattr(flux_module.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(flux_module, "_cuda_memory_gib", lambda: (4.0, 12.0))

    assert provider._resolve_memory_mode() == "cpu_offload"


def test_pipeline_load_uses_direct_cuda_device_map(monkeypatch, tmp_path) -> None:
    captured = {}

    class FakePipeline:
        pass

    def build_pipeline(repo_or_path, **kwargs):
        captured["repo_or_path"] = repo_or_path
        captured.update(kwargs)
        return FakePipeline()

    provider = FluxKleinImageProvider(
        {
            "local_dir": str(tmp_path),
            "device": "cuda",
            "enable_cpu_offload": False,
            "torch_dtype": "bfloat16",
        }
    )
    monkeypatch.setattr(flux_module, "validate_flux_pipeline_import", lambda: {"ok": True, "details": {"pipeline_class": "Flux2KleinPipeline"}})
    monkeypatch.setattr(flux_module, "get_flux_local_model_status", lambda _path: {"complete": True})
    monkeypatch.setattr(flux_module, "validate_flux_repo_runtime", lambda _path: {"ok": True})
    monkeypatch.setattr(flux_module, "build_flux_pipeline", build_pipeline)
    monkeypatch.setattr(flux_module.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(flux_module, "_cuda_memory_gib", lambda: (20.0, 24.0))

    assert provider._ensure_pipeline().__class__ is FakePipeline
    assert captured["repo_or_path"] == str(tmp_path)
    assert captured["device_map"] == "cuda"
    assert provider.runtime_status()["memory_mode"] == "cuda_direct"


def test_warmup_runs_representative_inference_without_saving_asset(monkeypatch) -> None:
    calls = []

    class FakePipeline:
        def __call__(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(images=[object()])

    provider = FluxKleinImageProvider(
        {
            "warmup_width": 768,
            "warmup_height": 768,
            "warmup_steps": 4,
        }
    )
    provider._pipeline = FakePipeline()
    provider._memory_mode = "cpu"
    monkeypatch.setattr(flux_module, "_release_generation_memory", lambda: None)
    monkeypatch.setattr(
        flux_module,
        "generated_images_root",
        lambda: (_ for _ in ()).throw(AssertionError("warmup must not write an asset")),
    )

    first = provider.warmup()
    second = provider.warmup()

    assert first["ok"] is True
    assert first["warmed_up"] is True
    assert first["skipped"] is False
    assert first["width"] == 768
    assert first["height"] == 768
    assert first["steps"] == 4
    assert second["skipped"] is True
    assert len(calls) == 1
    assert calls[0]["num_inference_steps"] == 4
    assert provider.runtime_status()["warmup_state"] == "completed"


def test_generation_budget_rejects_oversized_images() -> None:
    provider = FluxKleinImageProvider({"max_pixels": 1024 * 1024})

    error = provider._generation_budget_error(2048, 1024)

    assert error.startswith("flux_klein_image_too_large:")


def test_generation_budget_rejects_low_cuda_headroom(monkeypatch) -> None:
    provider = FluxKleinImageProvider({"min_generation_free_gib": 3})
    provider._memory_mode = "cuda_direct"
    monkeypatch.setattr(flux_module, "_cuda_memory_gib", lambda: (2.0, 24.0))

    error = provider._generation_budget_error(768, 768)

    assert error.startswith("flux_klein_insufficient_generation_vram:")


def test_build_flux_pipeline_forwards_device_map(monkeypatch) -> None:
    captured = {}

    class FakePipelineClass:
        @classmethod
        def from_pretrained(cls, repo_or_path, **kwargs):
            captured["repo_or_path"] = repo_or_path
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(
        flux_pipeline_compat,
        "resolve_flux_pipeline_class",
        lambda: (FakePipelineClass, "Flux2KleinPipeline"),
    )

    flux_pipeline_compat.build_flux_pipeline(
        "local-model",
        torch_dtype="bf16",
        local_files_only=True,
        device_map="cuda",
    )

    assert captured == {
        "repo_or_path": "local-model",
        "torch_dtype": "bf16",
        "local_files_only": True,
        "device_map": "cuda",
    }
