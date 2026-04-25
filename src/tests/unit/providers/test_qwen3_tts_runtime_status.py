import sys
import types

from app.providers.vendor.faster_qwen3_tts.model import (
    _ensure_transformers_qwen3_compat,
)
from app.providers.vendor.qwen3_tts.runtime_status import (
    validate_qwen3_tts_runtime,
)


def test_ensure_transformers_qwen3_compat_adds_missing_symbols(monkeypatch):
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.modeling_utils = types.ModuleType("transformers.modeling_utils")
    fake_transformers.utils = types.ModuleType("transformers.utils")

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    _ensure_transformers_qwen3_compat()

    assert hasattr(fake_transformers.modeling_utils, "ALL_ATTENTION_FUNCTIONS")
    assert fake_transformers.modeling_utils.ALL_ATTENTION_FUNCTIONS == {}
    assert hasattr(fake_transformers.utils, "auto_docstring")
    assert hasattr(fake_transformers.utils, "auto_class_docstring")
    assert callable(fake_transformers.utils.auto_docstring)
    assert callable(fake_transformers.utils.auto_class_docstring)


def test_ensure_transformers_qwen3_compat_overrides_broken_docstring_decorators(monkeypatch):
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.modeling_utils = types.ModuleType("transformers.modeling_utils")
    fake_transformers.utils = types.ModuleType("transformers.utils")

    def broken_auto_docstring(*args, **kwargs):
        raise UnboundLocalError("local variable 'docstring' referenced before assignment")

    def broken_auto_class_docstring(*args, **kwargs):
        raise UnboundLocalError("local variable 'docstring' referenced before assignment")

    fake_transformers.utils.auto_docstring = broken_auto_docstring
    fake_transformers.utils.auto_class_docstring = broken_auto_class_docstring

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "transformers.utils", fake_transformers.utils)

    _ensure_transformers_qwen3_compat()

    decorated = fake_transformers.utils.auto_docstring(lambda x: x)
    assert callable(decorated)

    class Sample:
        pass

    assert fake_transformers.utils.auto_class_docstring()(Sample) is Sample


def test_ensure_transformers_qwen3_compat_supports_bare_and_parameterized_use(monkeypatch):
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.modeling_utils = types.ModuleType("transformers.modeling_utils")
    fake_transformers.utils = types.ModuleType("transformers.utils")

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    _ensure_transformers_qwen3_compat()
    auto_docstring = fake_transformers.utils.auto_docstring

    class BareDecorated:
        pass

    decorated_bare = auto_docstring(BareDecorated)
    assert decorated_bare is BareDecorated

    class ParameterizedDecorated:
        pass

    decorated_parameterized = auto_docstring(custom_intro="ignored")(ParameterizedDecorated)
    assert decorated_parameterized is ParameterizedDecorated


def test_validate_qwen3_tts_runtime_returns_structured_failure_on_missing_vendor(monkeypatch):
    from app.providers.vendor import qwen3_tts as qwen3_tts_pkg
    from app.providers.vendor.qwen3_tts import runtime_status as runtime_status_module

    def _boom():
        raise RuntimeError("missing vendor")

    monkeypatch.setattr(runtime_status_module, "ensure_vendored_qwen3_tts_available", _boom)

    payload = validate_qwen3_tts_runtime()

    assert payload["provider"] == "qwen3_tts"
    assert payload["ready"] is False
    assert payload["status"] == "not_ready"
    assert payload["summary"] == "QWEN3_TTS NOT READY"
    assert "vendored_package_validation_failed:" in payload["error"]
    assert isinstance(payload["details"], dict)


def test_validate_qwen3_tts_runtime_returns_structured_payload(monkeypatch):
    from app.providers.vendor.qwen3_tts import runtime_status as runtime_status_module

    fake_numpy = types.SimpleNamespace(__version__="1.0")
    fake_torch = types.SimpleNamespace(
        __version__="2.0",
        cuda=types.SimpleNamespace(is_available=lambda: True),
    )
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.__version__ = "4.52.0"
    fake_transformers.modeling_utils = types.ModuleType("transformers.modeling_utils")
    fake_transformers.utils = types.ModuleType("transformers.utils")
    fake_tokenizers = types.SimpleNamespace(__version__="0.21.0")
    fake_accelerate = types.SimpleNamespace(__version__="1.6.0")
    fake_safetensors = types.SimpleNamespace(__version__="0.6.0")
    fake_safetensors.safe_open = lambda *args, **kwargs: object()
    fake_soundfile = types.SimpleNamespace(__version__="0.13.0")
    fake_qwen_tts = types.ModuleType("app.providers.vendor.qwen_tts")
    fake_qwen_tts.Qwen3TTSModel = object

    monkeypatch.setattr(runtime_status_module, "ensure_vendored_qwen3_tts_available", lambda: {"vendor_root": "/tmp/vendor"})
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "tokenizers", fake_tokenizers)
    monkeypatch.setitem(sys.modules, "accelerate", fake_accelerate)
    monkeypatch.setitem(sys.modules, "safetensors", fake_safetensors)
    monkeypatch.setitem(sys.modules, "soundfile", fake_soundfile)
    monkeypatch.setitem(sys.modules, "app.providers.vendor.qwen_tts", fake_qwen_tts)

    payload = validate_qwen3_tts_runtime()

    assert payload["provider"] == "qwen3_tts"
    assert payload["status"] == "ready"
    assert payload["ready"] is True
    assert payload["summary"] == "QWEN3_TTS READY"
    assert payload["error"] == ""
    assert "versions" in payload["details"]
    assert "compat" in payload["details"]
    assert payload["details"]["compat"]["shim_has_auto_docstring"] is True
    assert payload["details"]["compat"]["shim_has_all_attention_functions"] is True
    assert payload["details"]["compat"]["shim_patched_safetensors_metadata"] is True


def test_transformers_masking_utils_shim_exposes_create_masks_for_generate():
    import importlib
    import sys

    from app.providers.vendor.faster_qwen3_tts.model import (
        _ensure_transformers_qwen3_compat,
    )

    # Clear any existing module first and save original
    original = sys.modules.pop("transformers.masking_utils", None)

    try:
        # Apply compat shims
        _ensure_transformers_qwen3_compat()

        # Import the module
        masking_utils = importlib.import_module("transformers.masking_utils")

        # Verify the symbol exists and is callable
        assert hasattr(masking_utils, "create_masks_for_generate")
        assert callable(masking_utils.create_masks_for_generate)
        assert hasattr(masking_utils, "prepare_decoder_attention_mask")
        assert callable(masking_utils.prepare_decoder_attention_mask)
        assert hasattr(masking_utils, "prepare_attention_mask_for_generation")
        assert callable(masking_utils.prepare_attention_mask_for_generation)
        
        # Verify they return None as expected
        assert masking_utils.create_masks_for_generate() is None
        assert masking_utils.prepare_decoder_attention_mask() is None
        assert masking_utils.prepare_attention_mask_for_generation() is None
    finally:
        # Restore original module if it existed
        if original is not None:
            sys.modules["transformers.masking_utils"] = original


def test_transformers_modeling_utils_safe_open_is_rebound(monkeypatch):
    import types

    import transformers.modeling_utils as modeling_utils

    from app.providers.vendor.faster_qwen3_tts.model import (
        _ensure_transformers_qwen3_compat,
    )

    class _Handle:
        def metadata(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_safetensors = types.SimpleNamespace()
    fake_safetensors.safe_open = lambda *args, **kwargs: _Handle()
    fake_safetensors._omnix_metadata_patch_applied = False

    monkeypatch.setitem(__import__("sys").modules, "safetensors", fake_safetensors)

    _ensure_transformers_qwen3_compat()

    with modeling_utils.safe_open("dummy", framework="pt") as handle:
        assert handle.metadata() == {"format": "pt"}


def test_gradient_checkpointing_layer_shim_is_module_subclass():
    import importlib
    import sys

    import torch.nn as nn

    from app.providers.vendor.faster_qwen3_tts.model import (
        _ensure_transformers_qwen3_compat,
    )

    if "transformers.modeling_layers" in sys.modules:
        del sys.modules["transformers.modeling_layers"]

    _ensure_transformers_qwen3_compat()

    modeling_layers = importlib.import_module("transformers.modeling_layers")
    layer_cls = modeling_layers.GradientCheckpointingLayer

    assert issubclass(layer_cls, nn.Module)
    instance = layer_cls()
    assert isinstance(instance, nn.Module)
