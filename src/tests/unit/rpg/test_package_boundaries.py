"""Static ownership guards for the RPG package (WP-3.3d, WP-3.8, ADR-0015)."""
from __future__ import annotations

import ast
from pathlib import Path

RPG_ROOT = Path(__file__).resolve().parents[3] / "app" / "rpg"


def _production_modules() -> list[tuple[Path, ast.Module]]:
    modules = []
    for path in sorted(RPG_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        modules.append((path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))))
    return modules


def _relative(path: Path) -> str:
    return path.relative_to(RPG_ROOT).as_posix()


def test_rpg_production_code_never_imports_test_packages() -> None:
    offenders = []
    for path, tree in _production_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            offenders.extend(
                f"{_relative(path)}:{node.lineno}:{name}"
                for name in names
                if name == "tests" or name.startswith("tests.")
            )

    assert offenders == []


def test_rpg_package_has_no_test_modules() -> None:
    misplaced = [
        _relative(path)
        for path, _ in _production_modules()
        if path.name.startswith("test_") or "tests" in path.relative_to(RPG_ROOT).parts
    ]

    assert misplaced == []


def test_rpg_runtime_is_composed_from_static_modules() -> None:
    runtime_parts = [_relative(path) for path, _ in _production_modules() if path.name.startswith("runtime_part")]
    star_imports = []
    globals_calls = []
    for path, tree in _production_modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                star_imports.append(f"{_relative(path)}:{node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "globals":
                globals_calls.append(f"{_relative(path)}:{node.lineno}")

    assert runtime_parts == []
    assert star_imports == []
    assert globals_calls == []
