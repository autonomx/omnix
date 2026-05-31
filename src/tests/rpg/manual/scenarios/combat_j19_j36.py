from __future__ import annotations

from typing import Any, Dict

from tests.rpg.manual.scenarios.combat_j19_j36_runtime import COMBAT_J19_J36_SCENARIOS as _COMBAT_J19_J36_RUNTIME
from tests.rpg.manual.scenarios.combat_j19_j36_rewards_cleanup import COMBAT_J19_J36_SCENARIOS as _COMBAT_J19_J36_REWARDS_CLEANUP


COMBAT_J19_J36_SCENARIOS: Dict[str, Dict[str, Any]] = {
    **_COMBAT_J19_J36_RUNTIME,
    **_COMBAT_J19_J36_REWARDS_CLEANUP,
}
