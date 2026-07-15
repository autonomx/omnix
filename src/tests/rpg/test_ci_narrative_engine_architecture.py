from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = REPO_ROOT / "src" / "app" / "rpg" / "narrative_engine"
PROHIBITED_IMPORT_PREFIXES = (
    "app.rpg.ai.compact_dialogue",
    "app.rpg.ai.world_scene_narrator",
    "app.rpg.narration.runtime_narration_legacy",
    "app.rpg.session.first_call_dialogue",
    "app.rpg.response_generation.legacy_bridge",
)


def _prohibited(module: str) -> bool:
    return any(module == prefix or module.startswith(f"{prefix}.") for prefix in PROHIBITED_IMPORT_PREFIXES)


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def test_narrative_engine_does_not_import_legacy_generation_modules() -> None:
    assert ENGINE_ROOT.is_dir()
    violations: list[str] = []
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        for line, module in _imports(path):
            if _prohibited(module):
                relative = path.relative_to(REPO_ROOT).as_posix()
                violations.append(f"{relative}:{line}: {module}")
    assert violations == []
