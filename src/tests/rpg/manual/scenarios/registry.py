from __future__ import annotations

from typing import Any, Dict

try:
    from tests.rpg.manual.scenarios.combat_j19_j36 import COMBAT_J19_J36_SCENARIOS
except Exception:
    COMBAT_J19_J36_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.combat_k1_k9 import COMBAT_K1_K9_SCENARIOS
except Exception:
    COMBAT_K1_K9_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.narration_n1_n3 import NARRATION_N1_N3_SCENARIOS
except Exception:
    NARRATION_N1_N3_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.interactions_l1_l3 import (
        INTERACTION_L1_L3_SCENARIOS,
    )
except Exception:
    INTERACTION_L1_L3_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.spatial_l4_l6 import SPATIAL_L4_L6_SCENARIOS
except Exception:
    SPATIAL_L4_L6_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.memory_l7_l9 import MEMORY_L7_L9_SCENARIOS
except Exception:
    MEMORY_L7_L9_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.services_core import SERVICES_CORE_SCENARIOS
except Exception:
    SERVICES_CORE_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.conversation_core import CONVERSATION_CORE_SCENARIOS
except Exception:
    CONVERSATION_CORE_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.npc_social_memory import NPC_SOCIAL_MEMORY_SCENARIOS
except Exception:
    NPC_SOCIAL_MEMORY_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.npc_evolution_companions import (
        NPC_EVOLUTION_COMPANIONS_SCENARIOS,
    )
except Exception:
    NPC_EVOLUTION_COMPANIONS_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.inventory_m2_m8 import INVENTORY_M2_M8_SCENARIOS
except Exception:
    INVENTORY_M2_M8_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.scene_activities import SCENE_ACTIVITY_SCENARIOS
except Exception:
    SCENE_ACTIVITY_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.social_l10_l12 import SOCIAL_L10_L12_SCENARIOS
except Exception:
    SOCIAL_L10_L12_SCENARIOS = {}

try:
    from tests.rpg.manual.scenarios.quest_puzzle_l13_l15 import (
        QUEST_PUZZLE_L13_L15_SCENARIOS,
    )
except Exception:
    QUEST_PUZZLE_L13_L15_SCENARIOS = {}


def build_service_scenarios(
    legacy_scenarios: Dict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Dict[str, Any]]:
    scenarios: Dict[str, Dict[str, Any]] = {}
    if legacy_scenarios:
        scenarios.update(legacy_scenarios)

    for group in [
        COMBAT_J19_J36_SCENARIOS,
        COMBAT_K1_K9_SCENARIOS,
        NARRATION_N1_N3_SCENARIOS,
        INTERACTION_L1_L3_SCENARIOS,
        SPATIAL_L4_L6_SCENARIOS,
        MEMORY_L7_L9_SCENARIOS,
        SERVICES_CORE_SCENARIOS,
        CONVERSATION_CORE_SCENARIOS,
        NPC_SOCIAL_MEMORY_SCENARIOS,
        NPC_EVOLUTION_COMPANIONS_SCENARIOS,
        INVENTORY_M2_M8_SCENARIOS,
        SCENE_ACTIVITY_SCENARIOS,
        SOCIAL_L10_L12_SCENARIOS,
        QUEST_PUZZLE_L13_L15_SCENARIOS,
    ]:
        overlap = set(scenarios).intersection(group)
        if overlap:
            raise RuntimeError(f"duplicate_manual_scenario_names:{sorted(overlap)}")
        scenarios.update(group)

    return scenarios