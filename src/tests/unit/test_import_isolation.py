import sys
from types import ModuleType

import pytest

from src.tests.import_isolation import AppImportIsolation


def test_import_namespace_is_restored_and_reactivated(monkeypatch):
    parent = ModuleType("app.isolation_test")
    parent.__path__ = []
    original = ModuleType("app.isolation_test.child")
    parent.child = original
    monkeypatch.setitem(sys.modules, parent.__name__, parent)
    monkeypatch.setitem(sys.modules, original.__name__, original)
    replacement = ModuleType(original.__name__)
    extra = ModuleType("app.isolation_test.extra")
    finder = object()
    before_meta = list(sys.meta_path)
    state = AppImportIsolation()
    with pytest.raises(RuntimeError, match="collection failed"):
        with state.activate():
            sys.meta_path.insert(0, finder)
            sys.modules[original.__name__] = replacement
            sys.modules[extra.__name__] = extra
            parent.child = replacement
            parent.extra = extra
            raise RuntimeError("collection failed")
    assert sys.meta_path == before_meta
    assert sys.modules[original.__name__] is original
    assert extra.__name__ not in sys.modules
    assert parent.child is original
    assert not hasattr(parent, "extra")
    with state.activate():
        assert sys.modules[original.__name__] is replacement
        assert parent.child is replacement
        assert sys.modules[extra.__name__] is extra
        assert parent.extra is extra
        assert sys.meta_path[0] is finder
    assert sys.modules[original.__name__] is original
    assert not hasattr(parent, "extra")
    assert sys.meta_path == before_meta


def test_removed_app_module_is_restored(monkeypatch):
    original = ModuleType("app.isolation_removed_test")
    monkeypatch.setitem(sys.modules, original.__name__, original)
    with AppImportIsolation().activate():
        sys.modules.pop(original.__name__)
    assert sys.modules[original.__name__] is original
