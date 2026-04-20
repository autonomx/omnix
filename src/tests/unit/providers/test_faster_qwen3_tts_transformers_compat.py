import sys
import types

from app.providers.vendor.faster_qwen3_tts.model import (
    _ensure_transformers_qwen3_compat,
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
    assert callable(fake_transformers.utils.auto_docstring)


def test_auto_docstring_fallback_supports_bare_and_parameterized_usage(monkeypatch):
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

    decorated_with_kwargs = auto_docstring(custom_intro="ignored")(ParameterizedDecorated)
    assert decorated_with_kwargs is ParameterizedDecorated


def test_ensure_transformers_qwen3_compat_preserves_existing_auto_docstring(monkeypatch):
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.modeling_utils = types.ModuleType("transformers.modeling_utils")
    fake_transformers.utils = types.ModuleType("transformers.utils")

    sentinel = object()
    fake_transformers.utils.auto_docstring = sentinel

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    _ensure_transformers_qwen3_compat()

    assert fake_transformers.utils.auto_docstring is sentinel