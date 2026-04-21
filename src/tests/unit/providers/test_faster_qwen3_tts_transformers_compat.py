import sys
import types
import importlib

from app.providers.vendor.faster_qwen3_tts.model import (
    _ensure_transformers_qwen3_compat,
)


def _install_fake_transformers(monkeypatch):
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.modeling_utils = types.ModuleType("transformers.modeling_utils")
    fake_transformers.configuration_utils = types.ModuleType("transformers.configuration_utils")
    fake_transformers.utils = types.ModuleType("transformers.utils")
    fake_transformers.utils.generic = types.ModuleType("transformers.utils.generic")

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "transformers.modeling_utils", fake_transformers.modeling_utils)
    monkeypatch.setitem(sys.modules, "transformers.configuration_utils", fake_transformers.configuration_utils)
    monkeypatch.setitem(sys.modules, "transformers.utils", fake_transformers.utils)
    monkeypatch.setitem(sys.modules, "transformers.utils.generic", fake_transformers.utils.generic)
    monkeypatch.setattr(importlib, "reload", lambda module: module)
    return fake_transformers


def test_ensure_transformers_qwen3_compat_adds_missing_symbols(monkeypatch):
    fake_transformers = _install_fake_transformers(monkeypatch)

    _ensure_transformers_qwen3_compat()

    assert hasattr(fake_transformers.modeling_utils, "ALL_ATTENTION_FUNCTIONS")
    assert fake_transformers.modeling_utils.ALL_ATTENTION_FUNCTIONS == {}

    assert hasattr(fake_transformers.utils, "auto_docstring")
    assert callable(fake_transformers.utils.auto_docstring)
    assert hasattr(fake_transformers.utils, "can_return_tuple")
    assert callable(fake_transformers.utils.can_return_tuple)


def test_auto_docstring_fallback_supports_bare_and_parameterized_usage(monkeypatch):
    fake_transformers = _install_fake_transformers(monkeypatch)

    _ensure_transformers_qwen3_compat()

    auto_docstring = fake_transformers.utils.auto_docstring

    class BareDecorated:
        pass

    decorated_bare = auto_docstring(BareDecorated)
    assert decorated_bare is BareDecorated

    class ParameterizedDecorated:
        pass

    decorated_with_kwargs = auto_docstring(custom_intro="ignored")(ParameterizedDecorated)
    assert decorated_with_kwargs is ParameterizedDecorated


def test_ensure_transformers_qwen3_compat_replaces_auto_docstring_with_compat_noop(monkeypatch):
    fake_transformers = _install_fake_transformers(monkeypatch)

    sentinel = object()
    fake_transformers.utils.auto_docstring = sentinel

    _ensure_transformers_qwen3_compat()

    assert fake_transformers.utils.auto_docstring is not sentinel
    assert callable(fake_transformers.utils.auto_docstring)


def test_check_model_inputs_fallback_supports_bare_and_parameterized_usage(monkeypatch):
    fake_transformers = _install_fake_transformers(monkeypatch)

    _ensure_transformers_qwen3_compat()

    check_model_inputs = fake_transformers.utils.generic.check_model_inputs

    def bare_usage():
        return "ok"

    assert check_model_inputs(bare_usage) is bare_usage

    def parameterized_usage():
        return "ok"

    assert check_model_inputs()(parameterized_usage) is parameterized_usage


def test_layer_type_validation_fallback_is_available(monkeypatch):
    fake_transformers = _install_fake_transformers(monkeypatch)

    _ensure_transformers_qwen3_compat()

    layer_type_validation = fake_transformers.configuration_utils.layer_type_validation
    assert callable(layer_type_validation)
    assert layer_type_validation(["full_attention", "sliding_attention"]) is None
