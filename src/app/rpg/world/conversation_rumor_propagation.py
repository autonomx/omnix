"""Bounded rumor propagation for NPC conversations.

World signals from NPC conversations can seed rumors that apply soft pressure
to the world and can be consumed by later NPC interactions.

Hard constraints:
- Rumors do NOT create quests directly.
- Rumors do NOT create journal entries directly.
- Rumors do NOT move NPCs directly.
- Rumors do NOT change shops, money, inventory, rewards, or combat state.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

MAX_RUMOR_SEEDS = 16
MAX_RUMOR_MENTIONS_PER_LOCATION = 4

# Signal kinds that are eligible to seed rumors.
RUMOR_SEED_SIGNAL_KINDS = {
    "rumor_pressure",
    "quest_interest",
    "danger_warning",
    "social_tension",
}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def ensure_rumor_propagation_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    state = simulation_state.get("rumor_propagation_state")
    if not isinstance(state, dict):
        state = {}
        simulation_state["rumor_propagation_state"] = state
    if not isinstance(state.get("rumor_seeds"), list):
        state["rumor_seeds"] = []
    if not isinstance(state.get("location_mention_counts"), dict):
        state["location_mention_counts"] = {}
    if not isinstance(state.get("debug"), dict):
        state["debug"] = {}
    return state


def add_rumor_seed(
    simulation_state: Dict[str, Any],
    *,
    signal: Dict[str, Any],
    topic: Dict[str, Any],
    tick: int,
    location_id: str,
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """Add a bounded rumor seed from a world signal, if eligible.

    Returns the created seed dict, or {} if not added (disabled, wrong signal
    kind, dedup hit, or location cap reached).
    """
    signal = _safe_dict(signal)
    topic = _safe_dict(topic)
    settings = _safe_dict(settings)
    location_id = _safe_str(location_id)

    if not settings.get("allow_rumor_propagation", True):
        return {}

    signal_kind = _safe_str(signal.get("kind"))
    if signal_kind not in RUMOR_SEED_SIGNAL_KINDS:
        return {}

    topic_id = _safe_str(topic.get("topic_id") or signal.get("topic_id"))
    if not topic_id:
        return {}

    current_tick = int(tick or 0)

    # Always purge stale seeds before deduping. Otherwise an expired
    # topic/location seed can remain in state and block or appear as the
    # still-active seed at its expiry boundary.
    expire_stale_signals(
        simulation_state,
        current_tick=current_tick,
        settings=settings,
    )

    state = ensure_rumor_propagation_state(simulation_state)
    seeds = _safe_list(state.get("rumor_seeds"))
    max_seeds = max(0, _safe_int(settings.get("max_rumor_seeds"), MAX_RUMOR_SEEDS))

    # Dedup: one seed per topic+location combination.
    for existing in seeds:
        existing = _safe_dict(existing)
        if (
            _safe_str(existing.get("source_topic_id")) == topic_id
            and _safe_str(existing.get("location_id")) == location_id
        ):
            return {}

    # Location cap: don't exceed max_rumor_mentions_per_location.
    location_counts = _safe_dict(state.get("location_mention_counts"))
    location_count = _safe_int(location_counts.get(location_id), 0)
    max_per_location = max(0, _safe_int(settings.get("max_rumor_mentions_per_location"), MAX_RUMOR_MENTIONS_PER_LOCATION))
    if location_count >= max_per_location:
        return {}

    max_age = max(1, _safe_int(settings.get("max_signal_age_ticks"), 20))
    mentions = max(1, max_per_location - location_count)
    seed = {
        "seed_id": f"rumor_seed:{current_tick}:{topic_id}:{location_id}",
        "source_topic_id": topic_id,
        "source_topic_type": _safe_str(topic.get("topic_type") or signal.get("topic_type")),
        "source_signal_kind": signal_kind,
        "source_signal_id": _safe_str(signal.get("signal_id")),
        "location_id": location_id,
        "mentions_remaining": mentions,
        "strength": min(3, max(1, _safe_int(signal.get("strength"), 1))),
        "created_tick": current_tick,
        "expires_tick": current_tick + max_age,
        "source": "deterministic_rumor_propagation_runtime",
    }

    seeds.append(seed)
    if len(seeds) > max_seeds:
        del seeds[:-max_seeds]
    state["rumor_seeds"] = seeds

    location_counts[location_id] = location_count + 1
    state["location_mention_counts"] = location_counts

    state["debug"] = {
        "last_update": "add_rumor_seed",
        "seed_id": seed["seed_id"],
        "location_id": location_id,
        "tick": current_tick,
    }

    return deepcopy(seed)


def get_active_rumor_seeds(
    simulation_state: Dict[str, Any],
    *,
    location_id: str = "",
    current_tick: int = 0,
    settings: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Return active (non-expired, mentions > 0) rumor seeds.

    Optionally filtered by location_id.
    """
    state = ensure_rumor_propagation_state(simulation_state)
    seeds = _safe_list(state.get("rumor_seeds"))
    result = []
    for seed in seeds:
        seed = _safe_dict(seed)
        expires = _safe_int(seed.get("expires_tick"), 0)
        if expires and current_tick >= expires:
            continue
        if _safe_int(seed.get("mentions_remaining"), 0) <= 0:
            continue
        if location_id and _safe_str(seed.get("location_id")) != location_id:
            continue
        result.append(deepcopy(seed))
    return result


def expire_stale_signals(
    simulation_state: Dict[str, Any],
    *,
    current_tick: int,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Remove expired rumor seeds in place.  Returns a summary dict."""
    state = ensure_rumor_propagation_state(simulation_state)
    seeds = _safe_list(state.get("rumor_seeds"))
    active: List[Dict[str, Any]] = []
    expired_count = 0
    for seed in seeds:
        seed = _safe_dict(seed)
        expires = _safe_int(seed.get("expires_tick"), 0)
        if expires and current_tick >= expires:
            expired_count += 1
            continue
        active.append(seed)
    state["rumor_seeds"] = active
    return {
        "expired_count": expired_count,
        "remaining_count": len(active),
        "current_tick": current_tick,
        "source": "deterministic_rumor_propagation_runtime",
    }


def consume_rumor_seed_mention(
    simulation_state: Dict[str, Any],
    seed_id: str,
) -> bool:
    """Decrement mentions_remaining for a seed; remove it when exhausted.

    Returns True if a mention was consumed, False if the seed was not found or
    already exhausted.
    """
    state = ensure_rumor_propagation_state(simulation_state)
    seeds = _safe_list(state.get("rumor_seeds"))
    for seed in seeds:
        if _safe_str(_safe_dict(seed).get("seed_id")) == _safe_str(seed_id):
            remaining = _safe_int(_safe_dict(seed).get("mentions_remaining"), 0)
            if remaining <= 0:
                return False
            seed["mentions_remaining"] = remaining - 1
            state["rumor_seeds"] = seeds
            return True
    return False


def get_conversation_rumor_context(
    simulation_state: Dict[str, Any],
    *,
    location_id: str,
    current_tick: int = 0,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return active rumor context for a location (inspector / debug use)."""
    active_seeds = get_active_rumor_seeds(
        simulation_state,
        location_id=location_id,
        current_tick=current_tick,
        settings=settings,
    )
    return {
        "location_id": location_id,
        "active_seed_count": len(active_seeds),
        "active_seeds": active_seeds,
        "current_tick": current_tick,
        "source": "deterministic_rumor_propagation_runtime",
    }
