"""scripts/test_module.py maps every catalog module to its tests (PA-2.5)."""
from __future__ import annotations

import ast

import pytest

from app.runtime.feature_catalog import FEATURE_CATALOG
from scripts import test_module as module_tests


@pytest.mark.parametrize("module_id", sorted(FEATURE_CATALOG))
def test_every_catalog_module_has_a_test_directory_with_tests(module_id: str) -> None:
    directory, *_scenarios = module_tests.targets(module_id)

    assert directory.is_dir()
    assert any(directory.rglob("test_*.py")), f"{module_id} has no tests in {directory.name}"


def test_a_nested_package_uses_its_own_name() -> None:
    assert module_tests.module_test_directory("app.apps.rpg.edge.hermes").name == "hermes"
    assert module_tests.module_test_directory("app.platform.agent_runtime").name == "agent_runtime"


def test_characterization_scenarios_name_catalog_modules() -> None:
    named: set[str] = set()
    for path in module_tests.CHARACTERIZATION.glob("test_*.py"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and any(getattr(target, "id", None) == "MODULES" for target in node.targets):
                named.update(ast.literal_eval(node.value))

    assert named <= set(FEATURE_CATALOG)
    assert [path.name for path in module_tests.characterization_scenarios("rpg")] == ["test_rpg_production_turn.py"]


def test_an_unknown_module_is_refused() -> None:
    with pytest.raises(SystemExit, match="unknown module"):
        module_tests.targets("not-a-module")
