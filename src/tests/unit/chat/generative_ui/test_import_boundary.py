"""Pinned market data is read-only by construction (GUI-4.2)."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import app.platform.chat.generative_ui as generative_ui
from app.apps.trading.assistant_tool import TradingChatMarketSymbols

PACKAGE = Path(generative_ui.__file__).parent


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_chat_generative_ui_never_imports_trading():
    for path in PACKAGE.glob("*.py"):
        modules = _imported_modules(ast.parse(path.read_text(encoding="utf-8")))
        assert not any(module.startswith("app.apps") for module in modules), path.name


def test_the_trading_symbol_lookup_reaches_only_read_only_catalogs():
    tree = ast.parse(inspect.getsource(TradingChatMarketSymbols))
    modules = _imported_modules(tree)

    assert modules == {"app.apps.trading.catalog", "app.apps.trading.instrument_catalog_service"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    for write_path in ("order", "alert", "watchlist", "strategy", "paper", "broker"):
        assert not [name for name in names if write_path in name.casefold()], write_path
