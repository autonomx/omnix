"""Run one catalog module's tests (PA-2.5).

    python scripts/test_module.py <module_id> [pytest arguments...]
    python scripts/test_module.py <module_id> --list

A module's tests are `src/tests/<package>/`, named after the last part of its
Python package in the feature catalog (`agent-runtime` -> `agent_runtime`,
`hermes` -> `app.apps.rpg.edge.hermes` -> `hermes`), plus the characterization scenarios
that list the module in their `MODULES` tuple. Tests that span modules stay in
the cross-cutting directories (`kernel/`, `e2e/`, `characterization/`, `support/`).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "src" / "tests"
CHARACTERIZATION = TESTS / "characterization"


def catalog() -> dict[str, str]:
    """Catalog module id -> its Python package (`app.apps.rpg.edge.hermes`)."""
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from app.runtime.feature_catalog import FEATURE_CATALOG

    return {module_id: target.split(":", 1)[0].removesuffix(".feature") for module_id, target in FEATURE_CATALOG.items()}


def module_test_directory(package: str) -> Path:
    return TESTS / package.rsplit(".", 1)[-1]


def characterization_scenarios(module_id: str) -> list[Path]:
    """The characterization tests whose module-level `MODULES` tuple lists module_id."""
    found = []
    for path in sorted(CHARACTERIZATION.glob("test_*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "MODULES" for target in node.targets)
                and module_id in ast.literal_eval(node.value)
            ):
                found.append(path)
    return found


def targets(module_id: str) -> list[Path]:
    packages = catalog()
    if module_id not in packages:
        raise SystemExit(f"unknown module {module_id!r}; catalog modules: {', '.join(sorted(packages))}")
    directory = module_test_directory(packages[module_id])
    if not directory.is_dir():
        raise SystemExit(f"{module_id} has no test directory {directory.relative_to(ROOT).as_posix()}")
    return [directory, *characterization_scenarios(module_id)]


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    module_id, extra = argv[0], argv[1:]
    paths = targets(module_id)
    if extra == ["--list"]:
        for path in paths:
            print(path.relative_to(ROOT).as_posix())
        return 0
    command = [sys.executable, "-m", "pytest", *(path.relative_to(ROOT).as_posix() for path in paths), *extra]
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
