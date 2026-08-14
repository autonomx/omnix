from __future__ import annotations

import ast
from pathlib import Path

from app.trading.models import AdjustmentMode, AssetClass, FeedType, InstrumentType, UsageScope


MODELS_PATH = Path("src/app/trading/models.py")


def test_string_enums_preserve_wire_values() -> None:
    values = (
        AssetClass.CRYPTO,
        InstrumentType.SPOT,
        FeedType.REST,
        UsageScope.PERSONAL_LOCAL,
        AdjustmentMode.RAW,
    )
    for value in values:
        assert isinstance(value, str)
        assert str(value) == value.value


def test_strenum_import_has_python310_fallback() -> None:
    tree = ast.parse(MODELS_PATH.read_text(encoding="utf-8"))
    guarded = False

    for node in tree.body:
        if not isinstance(node, ast.Try):
            continue
        imports_stdlib_strenum = any(
            isinstance(statement, ast.ImportFrom)
            and statement.module == "enum"
            and any(alias.name == "StrEnum" for alias in statement.names)
            for statement in node.body
        )
        if not imports_stdlib_strenum:
            continue

        for handler in node.handlers:
            catches_import_error = (
                isinstance(handler.type, ast.Name)
                and handler.type.id == "ImportError"
            )
            defines_fallback = any(
                isinstance(statement, ast.ClassDef)
                and statement.name == "StrEnum"
                for statement in handler.body
            )
            if catches_import_error and defines_fallback:
                guarded = True
                break

    assert guarded, "Trading models must remain importable on Python 3.10"
