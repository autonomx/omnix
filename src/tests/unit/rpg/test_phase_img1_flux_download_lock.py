from app.image.downloads import get_flux_local_model_status, normalize_flux_local_dir


def test_normalize_flux_local_dir_defaults_to_models_image_folder(monkeypatch):
    monkeypatch.setattr("app.shared.MODELS_DIR", r"F:\LLM\omnix\resources\models")
    path = normalize_flux_local_dir("", "image")
    assert path.endswith(r"resources\models\image\flux2-klein-4b")


def test_get_flux_local_model_status_reports_incomplete_when_missing(tmp_path):
    status = get_flux_local_model_status(str(tmp_path / "flux2-klein-4b"))
    assert status["complete"] is False
    assert "model_index.json" in status["missing"]
    assert "*.safetensors" in status["missing"]
