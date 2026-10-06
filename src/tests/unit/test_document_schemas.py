"""Every document kind has a registered shape; writes that break it are refused (WP-5.9)."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.persistence import document_schemas
from app.persistence.document_schemas import (
    DocumentShapeError,
    document_matches,
    register_document_schema,
    registered_document_kinds,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[3]
_STORE_METHODS = {"read", "read_versioned", "write", "update", "lock", "list", "list_for_session", "delete", "clear"}


def _owners() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location("check_document_shapes", ROOT / "scripts" / "check_document_shapes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.load_document_schemas()
    return module.DOCUMENT_SCHEMA_OWNERS


def _kinds_in_source() -> set[tuple[str, str]]:
    kinds: set[tuple[str, str]] = set()
    for path in (ROOT / "src" / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _STORE_METHODS:
                keywords = {item.arg: item.value for item in node.keywords if item.arg}
                module, record_type = keywords.get("module"), keywords.get("record_type")
                if isinstance(module, ast.Constant) and isinstance(record_type, ast.Constant):
                    kinds.add((str(module.value), str(record_type.value)))
    return kinds


def test_every_document_kind_in_the_code_has_a_shape() -> None:
    _owners()
    missing = sorted(_kinds_in_source() - registered_document_kinds())
    assert missing == [], f"register a document schema for {missing}"


class _Note(BaseModel):
    title: str
    pages: int = 0


@pytest.fixture
def note_kind():
    register_document_schema("test", "note", _Note)
    yield ("test", "note")
    with document_schemas._LOCK:
        document_schemas._SCHEMAS.pop(("test", "note"), None)


def test_a_write_with_the_wrong_shape_is_refused_without_echoing_the_payload(note_kind) -> None:
    validate_document(*note_kind, {"title": "Ok", "pages": 3})
    with pytest.raises(DocumentShapeError, match="pages") as caught:
        validate_document(*note_kind, {"title": "secret-title", "pages": "many"})
    assert "secret-title" not in str(caught.value) and "many" not in str(caught.value)


def test_an_unregistered_kind_is_refused_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_DOCUMENT_SCHEMAS_STRICT", "1")
    with pytest.raises(DocumentShapeError, match="no document schema"):
        validate_document("test", "unknown-kind", {})
    monkeypatch.setenv("OMNIX_DOCUMENT_SCHEMAS_STRICT", "0")
    validate_document("test", "unknown-kind", {})


def test_a_stored_mismatch_is_logged_and_counted_but_not_raised(note_kind, caplog) -> None:
    from app.observability.metrics import exposition

    with caplog.at_level("WARNING"):
        assert document_matches(*note_kind, {"pages": 1}, record_id="n1") is False
    assert any("document_shape_mismatch module=test record_type=note record_id=n1" in r.getMessage() for r in caplog.records)
    assert 'omnix_document_shape_mismatches_total{module="test",record_type="note"}' in exposition()[0].decode()
    assert document_matches(*note_kind, {"title": "fine"}) is True
