from app.rpg.visual.flux_pipeline_compat import (
    validate_flux_pipeline_import,
    validate_flux_python_stack,
)


def test_validate_flux_python_stack_reports_torchvision_runtime_failure(monkeypatch):
    import builtins

    real_import = builtins.__import__

    class FakeTorch:
        __version__ = "2.5.1+cu124"

    class FakeTorchVision:
        __version__ = "0.20.1"

    class FakeTransformers:
        __version__ = "4.57.3"

    class FakeDiffusers:
        __version__ = "0.37.0"

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "torch":
            return FakeTorch
        if name == "torchvision":
            if fromlist and "transforms" in fromlist:
                raise RuntimeError("operator torchvision::nms does not exist")
            return FakeTorchVision
        if name == "transformers":
            return FakeTransformers
        if name == "diffusers":
            return FakeDiffusers
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    payload = validate_flux_python_stack()
    assert payload["ok"] is False
    assert payload["error"].startswith("torchvision_runtime_failed:")
    assert "traceback" in (payload.get("details") or {})


def test_validate_flux_pipeline_import_bubbles_python_stack_failure(monkeypatch):
    import app.rpg.visual.flux_pipeline_compat as compat

    monkeypatch.setattr(
        compat,
        "validate_flux_python_stack",
        lambda: {
            "ok": False,
            "error": "torchvision_runtime_failed:RuntimeError('operator torchvision::nms does not exist')",
            "details": {"torch": "2.5.1+cu124", "torchvision": "0.20.1"},
        },
    )

    payload = validate_flux_pipeline_import()
    assert payload["ok"] is False
    assert payload["error"].startswith("torchvision_runtime_failed:")
    assert (payload.get("details") or {}).get("python_stack", {}).get("torch") == "2.5.1+cu124"
