from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import image_service_app
from app.image import downloads as image_downloads
from app.image.downloads import get_image_local_model_status


def test_download_does_not_load_selected_model(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: False)
    monkeypatch.setattr(
        image_service_app,
        "download_image_model",
        lambda provider: calls.append(("download", provider)) or {
            "ok": True,
            "provider": provider,
            "loaded": False,
        },
    )
    monkeypatch.setattr(
        image_service_app,
        "load_image_provider",
        lambda provider=None: calls.append(("load", provider or "flux_klein")),
    )
    monkeypatch.setattr(
        image_service_app,
        "_local_model_status",
        lambda provider: {
            "ok": provider == "krea2_turbo",
            "exists": provider == "krea2_turbo",
            "complete": provider == "krea2_turbo",
            "missing": [],
            "local_dir": f"resources/models/image/{provider}",
        },
    )

    with TestClient(image_service_app.app) as client:
        response = client.post(
            "/provider/download",
            json={"provider": "krea2_turbo"},
        )

    assert response.status_code == 200
    assert response.json()["loaded"] is False
    assert calls == [("download", "krea2_turbo")]


def test_image_service_forwards_request_scoped_hf_token(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(image_service_app, "is_image_generation_enabled", lambda: True)
    monkeypatch.setattr(image_service_app, "is_image_provider_loaded", lambda _provider=None: False)
    monkeypatch.setattr(
        image_service_app,
        "download_image_model",
        lambda provider, token: calls.append((provider, token)) or {
            "ok": True,
            "provider": provider,
            "loaded": False,
        },
    )
    monkeypatch.setattr(
        image_service_app,
        "_local_model_status",
        lambda provider: {
            "ok": True,
            "exists": True,
            "complete": True,
            "missing": [],
            "local_dir": f"resources/models/image/{provider}",
        },
    )

    with TestClient(image_service_app.app) as client:
        response = client.post(
            "/provider/download",
            json={"provider": "krea2_turbo", "hf_token": "hf_request_token"},
        )

    assert response.status_code == 200
    assert calls == [("krea2_turbo", "hf_request_token")]
    assert "hf_request_token" not in response.text


def _write_model_skeleton(root: Path, *, missing_second_shard: bool = False) -> None:
    (root / "scheduler").mkdir(parents=True)
    (root / "transformer").mkdir(parents=True)
    (root / "model_index.json").write_text(
        json.dumps({
            "_class_name": "Krea2Pipeline",
            "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
            "transformer": ["diffusers", "Krea2Transformer2DModel"],
        }),
        encoding="utf-8",
    )
    (root / "scheduler" / "scheduler_config.json").write_text("{}", encoding="utf-8")
    (root / "transformer" / "diffusion_pytorch_model.safetensors.index.json").write_text(
        json.dumps({
            "weight_map": {
                "layer.0": "diffusion_pytorch_model-00001-of-00002.safetensors",
                "layer.1": "diffusion_pytorch_model-00002-of-00002.safetensors",
            }
        }),
        encoding="utf-8",
    )
    (root / "transformer" / "diffusion_pytorch_model-00001-of-00002.safetensors").write_bytes(b"weights")
    if not missing_second_shard:
        (root / "transformer" / "diffusion_pytorch_model-00002-of-00002.safetensors").write_bytes(b"weights")


def test_explicit_hf_token_is_used_only_for_snapshot_download(monkeypatch, tmp_path):
    calls: list[dict[str, object]] = []

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        _write_model_skeleton(Path(str(kwargs["local_dir"])))

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=snapshot_download),
    )
    monkeypatch.setattr(
        image_downloads,
        "load_settings",
        lambda: {
            "image": {
                "krea2_turbo": {
                    "local_dir": str(tmp_path),
                    "download_dir": "image",
                }
            }
        },
    )
    monkeypatch.setattr(image_downloads, "save_settings", lambda _settings: None)

    result = image_downloads.download_image_model("krea2_turbo", "hf_direct_token")

    assert result["ok"] is True
    assert calls[0]["token"] == "hf_direct_token"
    assert "hf_token" not in result
    assert "hf_direct_token" not in json.dumps(result)


def test_status_without_explicit_dir_resolves_canonical_model_path(monkeypatch, tmp_path):
    canonical_dir = tmp_path / "image" / "flux2-klein-4b"
    _write_model_skeleton(canonical_dir)
    monkeypatch.setattr(image_downloads, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(
        image_downloads,
        "load_settings",
        lambda: {
            "image": {
                "flux_klein": {
                    "local_dir": "",
                    "download_dir": "image",
                }
            }
        },
    )

    status = get_image_local_model_status("flux_klein")

    assert Path(status["local_dir"]) == canonical_dir
    assert status["complete"] is True
    assert status["missing"] == []


def test_canonical_flux_download_wins_over_stale_configured_directory(monkeypatch, tmp_path):
    stale_dir = tmp_path / "stale-flux-path"
    stale_dir.mkdir()
    canonical_dir = tmp_path / "image" / "flux2-klein-4b"
    _write_model_skeleton(canonical_dir)
    monkeypatch.setattr(image_downloads, "MODELS_DIR", str(tmp_path))

    resolved = image_downloads.resolve_image_local_dir_from_settings(
        {
            "image": {
                "flux_klein": {
                    "local_dir": str(stale_dir),
                    "download_dir": "image",
                }
            }
        },
        "flux_klein",
    )

    assert Path(resolved) == canonical_dir
    status = get_image_local_model_status("flux_klein", resolved)
    assert status["complete"] is True
    assert status["missing"] == []


def test_partial_sharded_snapshot_is_not_reported_as_downloaded(tmp_path):
    _write_model_skeleton(tmp_path, missing_second_shard=True)

    status = get_image_local_model_status("krea2_turbo", str(tmp_path))

    assert status["complete"] is False
    assert "transformer/diffusion_pytorch_model-00002-of-00002.safetensors" in status["missing"]


def test_complete_sharded_snapshot_is_reported_as_downloaded(tmp_path):
    _write_model_skeleton(tmp_path)

    status = get_image_local_model_status("krea2_turbo", str(tmp_path))

    assert status["complete"] is True
    assert status["missing"] == []


def test_hugging_face_incomplete_file_blocks_download_status(tmp_path):
    _write_model_skeleton(tmp_path)
    cache_dir = tmp_path / ".cache" / "huggingface" / "download"
    cache_dir.mkdir(parents=True)
    (cache_dir / "model.safetensors.incomplete").write_bytes(b"partial")

    status = get_image_local_model_status("krea2_turbo", str(tmp_path))

    assert status["complete"] is False
    assert any(item.startswith("incomplete:") for item in status["missing"])
