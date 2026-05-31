from __future__ import annotations

from typing import Any, Dict

from tests.rpg.manual.scenarios.combat_k1_k9_core import COMBAT_K1_K9_SCENARIOS as _COMBAT_K1_K9_CORE
from tests.rpg.manual.scenarios.combat_k1_k9_abilities import COMBAT_K1_K9_SCENARIOS as _COMBAT_K1_K9_ABILITIES
from tests.rpg.manual.scenarios.combat_k1_k9_companions_positioning import COMBAT_K1_K9_SCENARIOS as _COMBAT_K1_K9_COMPANIONS_POSITIONING


COMBAT_K1_K9_SCENARIOS: Dict[str, Dict[str, Any]] = {
    **_COMBAT_K1_K9_CORE,
    **_COMBAT_K1_K9_ABILITIES,
    **_COMBAT_K1_K9_COMPANIONS_POSITIONING,
}
