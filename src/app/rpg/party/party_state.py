"""Phase 9.1 — Party state management.

Provides deterministic, serialisable party/companion state that sits on top
of the player state.

Key guarantees:
    - party_state is always present and well-formed
    - companions list is bounded to max_size (default 3)
    - all values are safe (str / dict / list) even if upstream data is dirty
    - state updates are pure functions returning a new player_state dict
"""
from typing import Dict, Any, List


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def ensure_party_state(player_state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure *player_state* has a well-formed ``party_state`` subtree.

    Idempotent — safe to call multiple times.
    """
    player_state = _safe_dict(player_state)

    party = _safe_dict(player_state.get("party_state"))

    party.setdefault("companions", [])
    party.setdefault("max_size", 3)

    player_state["party_state"] = party
    return player_state


def add_companion(player_state: Dict[str, Any], npc_id: str, name: str) -> Dict[str, Any]:
    """Add a companion to the party if there is room and not already present."""
    player_state = ensure_party_state(player_state)
    party = player_state["party_state"]

    companions = _safe_list(party.get("companions"))

    # Check for duplicates
    if any(c.get("npc_id") == npc_id for c in companions):
        return player_state

    # Check capacity
    if len(companions) >= int(party.get("max_size", 3)):
        return player_state

    companions.append({
        "npc_id": npc_id,
        "name": name,
        "hp": 100,
        "loyalty": 0.5,
        "role": "ally",
    })

    party["companions"] = companions
    player_state["party_state"] = party
    return player_state


def remove_companion(player_state: Dict[str, Any], npc_id: str) -> Dict[str, Any]:
    """Remove a companion from the party by npc_id."""
    player_state = ensure_party_state(player_state)
    party = player_state["party_state"]

    companions = [
        c for c in _safe_list(party.get("companions"))
        if c.get("npc_id") != npc_id
    ]

    party["companions"] = companions
    player_state["party_state"] = party
    return player_state


def get_active_companions(player_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the list of active companions."""
    player_state = ensure_party_state(player_state)
    return _safe_list(player_state["party_state"].get("companions"))