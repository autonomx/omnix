from app.rpg.visual.runtime_status import validate_flux_klein_runtime


def test_flux_runtime_hint_references_real_requirements_file(monkeypatch):
    import app.rpg.visual.runtime_status as runtime_status

    fake_versions = {}

    class FakeExc(ImportError):
        pass

    def fake_import_hh():
        class FakeHub:
            __version__ = "1.11.0"
        return FakeHub()

    original_import = __import__

    def patched_import(name, *args, **kwargs):
        if name == "numpy":
            class FakeNumpy:
                __version__ = "1.26.4"
            return FakeNumpy()
        if name == "torch":
            class FakeCuda:
                @staticmethod
                def is_available():
                    return True
            class FakeTorch:
                __version__ = "2.5.1"
                cuda = FakeCuda()
            return FakeTorch()
        if name == "diffusers":
            class FakeDiffusers:
                __version__ = "0.35.2"
            return FakeDiffusers()
        if name == "huggingface_hub":
            return fake_import_hh()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(runtime_status, "__import__", patched_import, raising=False)

    payload = validate_flux_klein_runtime()
    assert payload["provider"] == "flux_klein"
    assert isinstance(payload["details"], dict)


def test_runtime_status_payload_is_structured():
    payload = validate_flux_klein_runtime()
    assert isinstance(payload, dict)
    assert payload.get("provider") == "flux_klein"
    assert payload.get("status") in {"ready", "not_ready"}
    assert isinstance(payload.get("ready"), bool)
    assert "summary" in payload
    assert "error" in payload
    assert isinstance(payload.get("details"), dict)