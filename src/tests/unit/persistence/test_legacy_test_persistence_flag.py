from __future__ import annotations

import ast
from pathlib import Path

from app.persistence.runtime import is_legacy_test_persistence

APP = Path(__file__).resolve().parents[3] / "app"


def test_the_flag_reads_the_mode_without_validating_it() -> None:
    assert is_legacy_test_persistence({"OMNIX_PERSISTENCE_MODE": " legacy_test "})
    assert not is_legacy_test_persistence({"OMNIX_PERSISTENCE_MODE": "postgresql"})
    assert not is_legacy_test_persistence({"OMNIX_PERSISTENCE_MODE": "bogus"})
    assert not is_legacy_test_persistence({})


def test_only_the_persistence_runtime_reads_the_mode() -> None:
    readers = []
    for path in sorted(APP.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and node.value == "OMNIX_PERSISTENCE_MODE":
                readers.append(path.relative_to(APP).as_posix())
    assert set(readers) <= {"persistence/runtime.py"}, "ask app.persistence.runtime.is_legacy_test_persistence"
