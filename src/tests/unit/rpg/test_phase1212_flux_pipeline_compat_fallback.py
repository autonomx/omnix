import types

from app.rpg.visual import flux_pipeline_compat as compat


def test_validate_flux_pipeline_import_uses_top_level_fluxpipeline(monkeypatch):
    fake_diffusers = types.SimpleNamespace(
        __version__="0.35.2",
        FluxPipeline=type("FluxPipeline", (), {}),
    )

    monkeypatch.setattr(compat, "importlib", compat.importlib)

    import builtins
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "diffusers":
            return fake_diffusers
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    payload = compat.validate_flux_pipeline_import()
    assert payload["ok"] is True
    assert payload["details"]["pipeline_class"] == "FluxPipeline"


def test_resolve_flux_pipeline_class_falls_back_to_submodule(monkeypatch):
    fake_diffusers = types.SimpleNamespace(__version__="0.35.2")
    fake_module = types.SimpleNamespace(FluxPipeline=type("FluxPipeline", (), {}))

    import builtins
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "diffusers":
            return fake_diffusers
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    real_import_module = compat.importlib.import_module

    def fake_import_module(name, package=None):
        if name == "diffusers.pipelines.flux.pipeline_flux":
            return fake_module
        return real_import_module(name, package)

    monkeypatch.setattr(compat.importlib, "import_module", fake_import_module)

    cls, resolved = compat.resolve_flux_pipeline_class()
    assert cls is fake_module.FluxPipeline
    assert resolved == "diffusers.pipelines.flux.pipeline_flux.FluxPipeline"