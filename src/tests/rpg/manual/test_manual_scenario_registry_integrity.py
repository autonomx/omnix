from __future__ import annotations

import ast
from pathlib import Path
from typing import Set

from tests.rpg.manual.runner import build_service_scenarios
from tests.rpg.manual.scenarios.expected_legacy_names import EXPECTED_LEGACY_SCENARIO_NAMES
from tests.rpg.manual.scenarios.expected_memory_l7_l9_names import (
    EXPECTED_MEMORY_L7_L9_SCENARIO_NAMES,
)
from tests.rpg.manual.scenarios.expected_social_l10_l12_names import (
    EXPECTED_SOCIAL_L10_L12_SCENARIO_NAMES,
)


def test_manual_scenario_registry_integrity():
    """Test that scenario source files have no duplicate dictionary keys and registry merges correctly."""

    # Test that build_service_scenarios() produces exactly the expected names
    scenarios = build_service_scenarios()
    names = set(scenarios.keys())

    # Combine legacy + memory L7-L9 + social L10-L12 + spatial L4-L6 (already in legacy)
    from tests.rpg.manual.scenarios.spatial_l4_l6 import SPATIAL_L4_L6_SCENARIOS
    all_expected = set(EXPECTED_LEGACY_SCENARIO_NAMES) | set(EXPECTED_MEMORY_L7_L9_SCENARIO_NAMES) | set(EXPECTED_SOCIAL_L10_L12_SCENARIO_NAMES) | set(SPATIAL_L4_L6_SCENARIOS.keys())

    missing = all_expected - names
    extra = names - all_expected

    assert not missing, f"Missing scenario names: {sorted(missing)}"
    assert not extra, f"Extra scenario names: {sorted(extra)}"
    assert len(names) == 177, f"Expected 177 scenario names, got {len(names)}"

    # Test source files for duplicate literal keys in scenario dictionaries
    scenario_files = [
        Path("src/tests/rpg/manual/scenarios/combat_j19_j36.py"),
        Path("src/tests/rpg/manual/scenarios/combat_k1_k9.py"),
        Path("src/tests/rpg/manual/scenarios/narration_n1_n3.py"),
        Path("src/tests/rpg/manual/scenarios/interactions_l1_l3.py"),
        Path("src/tests/rpg/manual/scenarios/spatial_l4_l6.py"),
        Path("src/tests/rpg/manual/scenarios/services_core.py"),
        Path("src/tests/rpg/manual/scenarios/conversation_core.py"),
        Path("src/tests/rpg/manual/scenarios/npc_social_memory.py"),
        Path("src/tests/rpg/manual/scenarios/npc_evolution_companions.py"),
        Path("src/tests/rpg/manual/scenarios/inventory_m2_m8.py"),
        Path("src/tests/rpg/manual/scenarios/scene_activities.py"),
        Path("src/tests/rpg/manual/scenarios/social_l10_l12.py"),
    ]

    for file_path in scenario_files:
        if not file_path.exists():
            continue

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise AssertionError(f"Scenario file has syntax error: {file_path}: {exc}") from exc

        duplicate_keys = _find_duplicate_dict_keys(tree)
        assert not duplicate_keys, f"File {file_path} contains duplicate dictionary keys: {duplicate_keys}"


def _find_duplicate_dict_keys(tree: ast.AST) -> Set[str]:
    """Find duplicate string literal keys in dictionary assignments ending with _SCENARIOS."""
    duplicates = set()

    def check_dict_node(target, value):
        if (isinstance(target, ast.Name) and
            target.id.endswith('_SCENARIOS') and
            isinstance(value, ast.Dict)):

            keys_seen = set()
            for key_node in value.keys:
                if isinstance(key_node, ast.Str):  # Python < 3.8
                    key = key_node.s
                elif hasattr(key_node, 'value'):  # Python >= 3.8
                    key = key_node.value
                else:
                    continue

                if key in keys_seen:
                    duplicates.add(key)
                else:
                    keys_seen.add(key)

    class DictVisitor(ast.NodeVisitor):
        def visit_Assign(self, node):
            # Check if this is an assignment to a name ending with _SCENARIOS
            if len(node.targets) == 1:
                check_dict_node(node.targets[0], node.value)
            self.generic_visit(node)

        def visit_AnnAssign(self, node):
            # Check if this is an annotated assignment to a name ending with _SCENARIOS
            check_dict_node(node.target, node.value)
            self.generic_visit(node)

    visitor = DictVisitor()
    visitor.visit(tree)
    return duplicates