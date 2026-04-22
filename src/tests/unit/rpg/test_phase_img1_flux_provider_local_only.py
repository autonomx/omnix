import pytest

from app.rpg.visual.providers.flux_klein_provider import FluxKleinImageProvider


def test_flux_provider_fails_when_local_model_missing_and_repo_fallback_disabled(monkeypatch, tmp_path):
    provider = FluxKleinImageProvider({
        "enabled": True,
        "download_dir": str(tmp_path),
        "local_dir": str(tmp_path / "flux2-klein-4b"),
        "prefer_local_files": True,
        "allow_repo_fallback": False,
    })

    monkeypatch.setattr(
        "app.rpg.visual.flux_pipeline_compat.validate_flux_pipeline_import",
        lambda: {"ok": True, "details": {"pipeline_class": "Flux2KleinPipeline"}},
    )

    with pytest.raises(RuntimeError) as exc:
        provider._ensure_pipeline()

    assert "flux_klein_local_model_missing:" in str(exc.value)
    assert "/api/image/models/flux-klein/download" in str(exc.value)
