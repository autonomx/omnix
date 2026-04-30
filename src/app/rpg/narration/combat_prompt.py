from __future__ import annotations

import json
from typing import Any, Dict


def build_combat_narration_prompt(contract: Dict[str, Any]) -> str:
    compact = json.dumps(contract, ensure_ascii=False, sort_keys=True)

    return f"""You are the narration layer for a deterministic RPG combat system.

You MUST narrate only the resolved combat facts provided below.
You MUST NOT invent combat outcomes.
You MUST NOT decide hits, misses, damage, defeat, loot, death, or turn order.
You MUST NOT mention JSON, system, prompt, contract, simulation, validation, or LLM.

Return strict JSON with exactly these keys:
{{
  "format_version": "rpg_narration_v2",
  "narration": "2-5 sentences of grounded combat narration.",
  "action": "Short resolved outcome, not the player's command.",
  "npc": {{"speaker": "", "line": ""}},
  "reward": "",
  "followup_hooks": []
}}

Combat contract:
{compact}
"""