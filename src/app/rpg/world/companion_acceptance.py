from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.party.party_state import add_companion, ensure_party_state
from app.rpg.world.npc_party_eligibility import evaluate_npc_party_join_eligibility


ACCEPTANCE_MARKERS = {
    "yes",
    "yeah",
    "agreed",
    "i accept",
    "join us",
    "join me",
    "come with me",
    "you can come",
    "welcome",
    "let's go",
    "lets go",
    "travel with me",
    "fight with me",
}

REJECTION_MARKERS = {
    "no",
    "not now",
    "stay here",
    "wait here",
    "i refuse",
    "don't come",
    "do not come",
    "go back",
}

MAX_PENDING_OFFERS = 8
MAX_ACCEPTANCE_HISTORY = 24


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _conversation_thread_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(simulation_state.get("conversation_thread_state"))
    if not state:
        state = {}
        simulation_state["conversation_thread_state"] = state
    if not isinstance(state.get("pending_companion_offers"), dict):
        state["pending_companion_offers"] = {}
    return state


def _mirror_pending_offers_to_conversation_state(simulation_state: Dict[str, Any]) -> None:
    acceptance_state = _safe_dict(simulation_state.get("companion_acceptance_state"))
    pending = _safe_dict(acceptance_state.get("pending_offers"))
    thread_state = _conversation_thread_state(simulation_state)
    thread_state["pending_companion_offers"] = deepcopy(pending)


def _hydrate_pending_offers_from_conversation_state(simulation_state: Dict[str, Any]) -> None:
    acceptance_state = ensure_companion_acceptance_state(simulation_state)
    pending = _safe_dict(acceptance_state.get("pending_offers"))
    if pending:
        return

    thread_state = _conversation_thread_state(simulation_state)
    mirrored = _safe_dict(thread_state.get("pending_companion_offers"))
    if mirrored:
        acceptance_state["pending_offers"] = deepcopy(mirrored)


def get_pending_companion_offer_debug(
    simulation_state: Dict[str, Any],
    *,
    player_input: str = "",
) -> Dict[str, Any]:
    """Small debug helper for manual transcript diagnostics.

    This intentionally exposes only deterministic state:
    - pending offer ids
    - whether the current player input matches accept/reject markers
    - where pending offers are visible
    """
    simulation_state = _safe_dict(simulation_state)
    acceptance_state = _safe_dict(simulation_state.get("companion_acceptance_state"))
    acceptance_pending = _safe_dict(acceptance_state.get("pending_offers"))
    thread_state = _safe_dict(simulation_state.get("conversation_thread_state"))
    thread_pending = _safe_dict(thread_state.get("pending_companion_offers"))

    return {
        "source": "deterministic_companion_acceptance_debug",
        "player_input": _safe_str(player_input),
        "accepts": player_input_accepts_companion_offer(player_input),
        "rejects": player_input_rejects_companion_offer(player_input),
        "acceptance_pending_count": len(acceptance_pending),
        "thread_pending_count": len(thread_pending),
        "acceptance_pending_npc_ids": sorted(_safe_str(key) for key in acceptance_pending.keys()),
        "thread_pending_npc_ids": sorted(_safe_str(key) for key in thread_pending.keys()),
        "has_any_pending_offer": bool(acceptance_pending or thread_pending),
    }


def hydrate_companion_acceptance_from_pending_offers(
    simulation_state: Dict[str, Any],
    pending_offers: Dict[str, Any],
) -> Dict[str, Any]:
    """Force companion_acceptance_state to see externally persisted offers.

    This is useful when the caller already sees pending offers in
    conversation_thread_state but the companion_acceptance_state copy was not
    restored yet.
    """
    pending_offers = _safe_dict(pending_offers)
    state = ensure_companion_acceptance_state(simulation_state)
    if pending_offers:
        state["pending_offers"] = deepcopy(pending_offers)
        _mirror_pending_offers_to_conversation_state(simulation_state)
    return state


def _text_has_any(text: str, markers: set[str]) -> bool:
    normalized = _safe_str(text).strip().lower()
    return any(marker in normalized for marker in markers)


def player_input_accepts_companion_offer(player_input: Any) -> bool:
    return _text_has_any(_safe_str(player_input), ACCEPTANCE_MARKERS)


def player_input_rejects_companion_offer(player_input: Any) -> bool:
    return _text_has_any(_safe_str(player_input), REJECTION_MARKERS)


def ensure_companion_acceptance_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    state = _safe_dict(simulation_state.get("companion_acceptance_state"))

    if not isinstance(state.get("pending_offers"), dict):
        state["pending_offers"] = {}

    if not isinstance(state.get("history"), list):
        state["history"] = []

    if not isinstance(state.get("debug"), dict):
        state["debug"] = {}

    simulation_state["companion_acceptance_state"] = state
    return state


def record_companion_join_offer(
    simulation_state: Dict[str, Any],
    *,
    npc_id: str,
    join_intent: Dict[str, Any],
    tick: int,
) -> Dict[str, Any]:
    npc_id = _safe_str(npc_id)
    intent = _safe_dict(join_intent)

    if not intent.get("offered"):
        return {
            "recorded": False,
            "reason": "join_intent_not_offered",
            "source": "deterministic_companion_acceptance",
        }

    state = ensure_companion_acceptance_state(simulation_state)
    pending = _safe_dict(state.get("pending_offers"))

    offer_id = f"companion_offer:{npc_id}:{int(tick or 0)}"
    eligibility = _safe_dict(intent.get("party_join_eligibility_result"))

    pending[npc_id] = {
        "offer_id": offer_id,
        "npc_id": npc_id,
        "created_tick": int(tick or 0),
        "status": "pending_player_acceptance",
        "reason": _safe_str(intent.get("reason") or "eligible_to_join"),
        "party_join_eligibility_result": deepcopy(eligibility),
        "source": "deterministic_companion_acceptance",
    }

    # Bound pending offers deterministically by oldest created_tick, then npc_id.
    ordered = sorted(
        pending.items(),
        key=lambda item: (
            int(_safe_dict(item[1]).get("created_tick") or 0),
            _safe_str(item[0]),
        ),
    )
    pending = dict(ordered[-MAX_PENDING_OFFERS:])

    state["pending_offers"] = pending
    state["debug"] = {
        "last_offer_id": offer_id,
        "last_npc_id": npc_id,
        "last_tick": int(tick or 0),
        "source": "deterministic_companion_acceptance",
    }
    _mirror_pending_offers_to_conversation_state(simulation_state)

    return {
        "recorded": True,
        "offer_id": offer_id,
        "npc_id": npc_id,
        "requires_player_acceptance": True,
        "source": "deterministic_companion_acceptance",
    }


def resolve_companion_acceptance(
    simulation_state: Dict[str, Any],
    *,
    npc_id: str,
    player_input: str,
    tick: int,
) -> Dict[str, Any]:
    npc_id = _safe_str(npc_id)
    _hydrate_pending_offers_from_conversation_state(simulation_state)
    state = ensure_companion_acceptance_state(simulation_state)
    pending = _safe_dict(state.get("pending_offers"))
    offer = _safe_dict(pending.get(npc_id))

    if not offer:
        return {
            "resolved": False,
            "accepted": False,
            "rejected": False,
            "reason": "no_pending_companion_offer",
            "source": "deterministic_companion_acceptance",
        }

    accepts = player_input_accepts_companion_offer(player_input)
    rejects = player_input_rejects_companion_offer(player_input)

    if not accepts and not rejects:
        return {
            "resolved": False,
            "accepted": False,
            "rejected": False,
            "reason": "player_response_did_not_resolve_offer",
            "offer": deepcopy(offer),
            "source": "deterministic_companion_acceptance",
        }

    history = _safe_list(state.get("history"))

    if rejects and not accepts:
        pending.pop(npc_id, None)
        entry = {
            "offer_id": _safe_str(offer.get("offer_id")),
            "npc_id": npc_id,
            "status": "rejected",
            "resolved_tick": int(tick or 0),
            "source": "deterministic_companion_acceptance",
        }
        history.append(entry)
        state["pending_offers"] = pending
        state["history"] = history[-MAX_ACCEPTANCE_HISTORY:]
        state["debug"] = deepcopy(entry)

        return {
            "resolved": True,
            "accepted": False,
            "rejected": True,
            "npc_id": npc_id,
            "reason": "player_rejected_companion_offer",
            "offer": deepcopy(offer),
            "source": "deterministic_companion_acceptance",
        }

    eligibility = evaluate_npc_party_join_eligibility(simulation_state, npc_id=npc_id)
    if not eligibility.get("eligible"):
        pending.pop(npc_id, None)
        entry = {
            "offer_id": _safe_str(offer.get("offer_id")),
            "npc_id": npc_id,
            "status": "invalidated",
            "resolved_tick": int(tick or 0),
            "reason": _safe_str(eligibility.get("reason") or "npc_no_longer_eligible"),
            "source": "deterministic_companion_acceptance",
        }
        history.append(entry)
        state["pending_offers"] = pending
        state["history"] = history[-MAX_ACCEPTANCE_HISTORY:]
        state["debug"] = deepcopy(entry)
        _mirror_pending_offers_to_conversation_state(simulation_state)

        return {
            "resolved": True,
            "accepted": False,
            "rejected": False,
            "npc_id": npc_id,
            "reason": "npc_no_longer_eligible",
            "party_join_eligibility_result": deepcopy(eligibility),
            "source": "deterministic_companion_acceptance",
        }

    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state = ensure_party_state(player_state)
    before_count = len(_safe_list(_safe_dict(player_state.get("party_state")).get("companions")))

    player_state = add_companion(
        player_state,
        npc_id,
        _safe_str(eligibility.get("name") or npc_id.replace("npc:", "")),
        role="companion",
        source="accepted_companion_offer",
        joined_tick=int(tick or 0),
        identity_arc=_safe_str(eligibility.get("identity_arc")),
        current_role=_safe_str(eligibility.get("current_role")),
        active_motivations=deepcopy(_safe_list(eligibility.get("active_motivations"))),
    )

    after_count = len(_safe_list(_safe_dict(player_state.get("party_state")).get("companions")))
    simulation_state["player_state"] = player_state

    pending.pop(npc_id, None)

    accepted = after_count > before_count or any(
        _safe_dict(comp).get("npc_id") == npc_id
        for comp in _safe_list(_safe_dict(player_state.get("party_state")).get("companions"))
    )

    entry = {
        "offer_id": _safe_str(offer.get("offer_id")),
        "npc_id": npc_id,
        "status": "accepted" if accepted else "not_added",
        "resolved_tick": int(tick or 0),
        "party_size_before": before_count,
        "party_size_after": after_count,
        "source": "deterministic_companion_acceptance",
    }
    history.append(entry)

    state["pending_offers"] = pending
    state["history"] = history[-MAX_ACCEPTANCE_HISTORY:]
    state["debug"] = deepcopy(entry)
    _mirror_pending_offers_to_conversation_state(simulation_state)

    return {
        "resolved": True,
        "accepted": bool(accepted),
        "rejected": False,
        "npc_id": npc_id,
        "reason": "player_accepted_companion_offer" if accepted else "party_state_not_changed",
        "offer": deepcopy(offer),
        "party_join_eligibility_result": deepcopy(eligibility),
        "party_state": deepcopy(player_state.get("party_state")),
        "source": "deterministic_companion_acceptance",
    }


def resolve_pending_companion_offer_response(
    simulation_state: Dict[str, Any],
    *,
    player_input: str,
    tick: int,
) -> Dict[str, Any]:
    """Resolve a pending companion offer from ordinary player input.

    This is intentionally independent from the conversation trigger gate.
    A pending offer is a simulation-owned state machine:

    offer pending -> player accepts/rejects -> party state mutates or offer clears

    It must work even when the current input is not wait/listen/observe/ambient.
    """
    _hydrate_pending_offers_from_conversation_state(simulation_state)
    state = ensure_companion_acceptance_state(simulation_state)
    pending = _safe_dict(state.get("pending_offers"))

    if not pending:
        return {
            "resolved": False,
            "accepted": False,
            "rejected": False,
            "reason": "no_pending_companion_offers",
            "debug": get_pending_companion_offer_debug(
                simulation_state,
                player_input=player_input,
            ),
            "source": "deterministic_companion_acceptance",
        }

    accepts = player_input_accepts_companion_offer(player_input)
    rejects = player_input_rejects_companion_offer(player_input)
    if not accepts and not rejects:
        return {
            "resolved": False,
            "accepted": False,
            "rejected": False,
            "reason": "player_response_did_not_resolve_any_pending_offer",
            "pending_offer_count": len(pending),
            "debug": get_pending_companion_offer_debug(
                simulation_state,
                player_input=player_input,
            ),
            "source": "deterministic_companion_acceptance",
        }

    normalized_input = _safe_str(player_input).lower()

    # Deterministic candidate selection:
    # 1. Prefer a pending NPC whose display/name token appears in player input.
    # 2. If exactly one pending offer exists, resolve it.
    # 3. Otherwise choose oldest created_tick, then npc_id for deterministic safety.
    candidates = []
    for npc_id, offer in pending.items():
        offer = _safe_dict(offer)
        candidate_name = _safe_str(
            offer.get("name")
            or _safe_dict(offer.get("party_join_eligibility_result")).get("name")
            or _safe_str(npc_id).replace("npc:", "")
        ).lower()
        mentioned = bool(candidate_name and candidate_name in normalized_input)
        candidates.append((
            0 if mentioned else 1,
            int(offer.get("created_tick") or 0),
            _safe_str(npc_id),
        ))

    candidates.sort()
    selected_npc_id = candidates[0][2] if candidates else ""
    if not selected_npc_id:
        return {
            "resolved": False,
            "accepted": False,
            "rejected": False,
            "reason": "no_selectable_pending_offer",
            "debug": get_pending_companion_offer_debug(
                simulation_state,
                player_input=player_input,
            ),
            "source": "deterministic_companion_acceptance",
        }

    result = resolve_companion_acceptance(
        simulation_state,
        npc_id=selected_npc_id,
        player_input=player_input,
        tick=tick,
    )
    result["resolved_from_pending_offer_response"] = True
    result["pending_offer_count_before_resolution"] = len(pending)
    return result
