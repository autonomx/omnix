"""Phase 16.1 — Memory lifecycle automation."""
from __future__ import annotations

from typing import Any, Dict

from app.rpg.memory.decay import decay_memory_state, reinforce_actor_memory


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def apply_dialogue_memory_hooks(
    simulation_state: Dict[str, Any],
    *,
    actor_id: str,
    player_text: str = "",
    reinforce_text: str = "",
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)

    # Deterministic decay on each dialogue lifecycle hook.
    simulation_state = decay_memory_state(simulation_state, decay_step=0.02)

    normalized_reinforce = _safe_str(reinforce_text).strip() or _safe_str(player_text).strip()
    if actor_id and normalized_reinforce:
        simulation_state = reinforce_actor_memory(
            simulation_state,
            actor_id=actor_id,
            text=normalized_reinforce[:240],
            amount=0.1,
        )

    return simulation_state
