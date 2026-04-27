from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
from typing import Any, Dict, List

MAX_SIGNAL_AGE_TICKS_DEFAULT = 10  # assume

def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(_safe_str(p) for p in parts)
    digest = sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"

def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}

def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v) if not isinstance(v, str) else v

def _safe_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _rumor_tombstones(runtime_state: Dict[str, Any]) -> Dict[str, int]:
    runtime_state = _safe_dict(runtime_state)
    tombstones = runtime_state.get("conversation_rumor_tombstones")
    if not isinstance(tombstones, dict):
        tombstones = {}
        runtime_state["conversation_rumor_tombstones"] = tombstones
    return tombstones


def _is_seed_tombstoned_this_tick(
    runtime_state: Dict[str, Any],
    *,
    seed_id: str,
    current_tick: int,
) -> bool:
    tombstones = _rumor_tombstones(runtime_state)
    return _safe_int(tombstones.get(seed_id), -1) == int(current_tick or 0)


def _tombstone_seed_this_tick(
    runtime_state: Dict[str, Any],
    *,
    seed_id: str,
    current_tick: int,
) -> None:
    if not seed_id:
        return
    tombstones = _rumor_tombstones(runtime_state)
    tombstones[seed_id] = int(current_tick or 0)

    # Keep this bounded.
    if len(tombstones) > 64:
        for key, _tick in sorted(tombstones.items(), key=lambda item: item[1])[:-64]:
            tombstones.pop(key, None)


def ensure_conversation_rumor_state(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(simulation_state.get("conversation_rumor_state"), dict):
        simulation_state["conversation_rumor_state"] = {}
    state = simulation_state["conversation_rumor_state"]
    if not isinstance(state.get("rumor_seeds"), list):
        state["rumor_seeds"] = []
    if not isinstance(state.get("debug"), dict):
        state["debug"] = {}
    if not isinstance(state.get("expired_seed_tombstones"), dict):
        state["expired_seed_tombstones"] = {}
    return state


def _seed_key(*, topic_id: str, location_id: str, signal_kind: str) -> str:
    return f"{_safe_str(topic_id)}::{_safe_str(location_id)}::{_safe_str(signal_kind)}"


def _seed_key_from_parts(*, topic_id: str, location_id: str, signal_kind: str) -> str:
    return f"{_safe_str(topic_id)}::{_safe_str(location_id)}::{_safe_str(signal_kind)}"


def _seed_key_from_seed(seed: Dict[str, Any]) -> str:
    seed = _safe_dict(seed)
    return _seed_key_from_parts(
        topic_id=_safe_str(seed.get("source_topic_id")),
        location_id=_safe_str(seed.get("location_id")),
        signal_kind=_safe_str(seed.get("signal_kind")),
    )


def expire_conversation_rumor_seeds(
    simulation_state: Dict[str, Any],
    *,
    current_tick: int,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Prune expired soft rumor seeds.

    Expiry is inclusive: a seed with expires_tick == current_tick is stale.
    The function also records per-tick tombstones so a just-expired seed is not
    recreated by a fresh signal in the same tick.
    """
    _ = settings
    state = ensure_conversation_rumor_state(simulation_state)
    seeds = _safe_list(state.get("rumor_seeds"))
    current_tick = int(current_tick or 0)
    kept: List[Dict[str, Any]] = []
    expired_ids: List[str] = []
    expired_keys: Dict[str, int] = {}
    for seed in seeds:
        seed = _safe_dict(seed)
        expires_tick = _safe_int(seed.get("expires_tick"), 0)
        if expires_tick and current_tick >= expires_tick:
            seed_id = _safe_str(seed.get("rumor_seed_id") or seed.get("seed_id"))
            if seed_id:
                expired_ids.append(seed_id)
            key = _seed_key_from_seed(seed)
            if key.strip(":"):
                expired_keys[key] = current_tick
            continue
        kept.append(seed)

    tombstones = _safe_dict(state.get("expired_seed_tombstones"))
    tombstones.update(expired_keys)
    state["rumor_seeds"] = kept
    state["expired_seed_tombstones"] = tombstones
    state["debug"] = {
        **_safe_dict(state.get("debug")),
        "last_seed_expiration_tick": int(current_tick or 0),
        "expired_seed_ids": expired_ids,
        "remaining_seed_count": len(kept),
    }
    state["debug"] = {
        **_safe_dict(state.get("debug")),
        "last_seed_expiration_tick": current_tick,
        "expired_seed_count": len(expired_ids),
        "expired_seed_ids": expired_ids,
    }
    return {
        "expired_count": len(seeds) - len(kept),
        "expired_seed_ids": expired_ids,
        "remaining_count": len(kept),
        "current_tick": int(current_tick or 0),
        "source": "deterministic_conversation_rumor_runtime",
    }


def expire_conversation_world_signals(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
    *,
    current_tick: int,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)
    settings = _safe_dict(settings)

    now = int(current_tick or 0)
    max_signal_age = max(1, _safe_int(settings.get("max_signal_age_ticks"), 3))

    rumor_state = _safe_dict(simulation_state.get("conversation_rumor_state"))
    thread_state = _safe_dict(simulation_state.get("conversation_thread_state"))

    expired_seed_ids: List[str] = []
    expired_signal_ids: List[str] = []

    # ── Expire rumor seeds ─────────────────────────────────────────────
    kept_seeds: List[Dict[str, Any]] = []
    for seed in _safe_list(rumor_state.get("rumor_seeds")):
        seed = _safe_dict(seed)
        seed_id = _safe_str(seed.get("seed_id"))
        expires_tick = _safe_int(seed.get("expires_tick"), 0)

        if seed_id and expires_tick and now >= expires_tick:
            expired_seed_ids.append(seed_id)
            _tombstone_seed_this_tick(runtime_state, seed_id=seed_id, current_tick=now)
            continue

        kept_seeds.append(seed)

    rumor_state["rumor_seeds"] = kept_seeds

    # ── Expire rumor-state signal mirror, if present ───────────────────
    kept_rumor_signals: List[Dict[str, Any]] = []
    for signal in _safe_list(rumor_state.get("conversation_world_signals")):
        signal = _safe_dict(signal)
        signal_id = _safe_str(signal.get("signal_id"))
        signal_tick = _safe_int(signal.get("tick"), now)
        expires_tick = _safe_int(signal.get("expires_tick"), 0)

        expired = bool(expires_tick and now >= expires_tick)
        if not expired:
            expired = now - signal_tick >= max_signal_age

        if expired:
            if signal_id:
                expired_signal_ids.append(signal_id)
            continue

        kept_rumor_signals.append(signal)

    rumor_state["conversation_world_signals"] = kept_rumor_signals

    # ── Expire canonical conversation_thread_state.world_signals ───────
    kept_thread_signals: List[Dict[str, Any]] = []
    for signal in _safe_list(thread_state.get("world_signals")):
        signal = _safe_dict(signal)
        signal_id = _safe_str(signal.get("signal_id"))
        signal_tick = _safe_int(signal.get("tick"), now)
        expires_tick = _safe_int(signal.get("expires_tick"), 0)

        expired = bool(expires_tick and now >= expires_tick)
        if not expired:
            expired = now - signal_tick >= max_signal_age

        if expired:
            if signal_id:
                expired_signal_ids.append(signal_id)
            continue

        kept_thread_signals.append(signal)

    thread_state["world_signals"] = kept_thread_signals

    debug = _safe_dict(rumor_state.get("debug"))
    debug["last_expiration"] = {
        "current_tick": now,
        "expired_seed_ids": expired_seed_ids,
        "expired_signal_ids": expired_signal_ids,
        "expired_count": len(expired_seed_ids) + len(expired_signal_ids),
        "remaining_seed_count": len(kept_seeds),
        "remaining_thread_signal_count": len(kept_thread_signals),
        "remaining_rumor_signal_count": len(kept_rumor_signals),
        "source": "deterministic_conversation_rumor_expiration",
    }
    rumor_state["debug"] = debug

    simulation_state["conversation_rumor_state"] = rumor_state
    simulation_state["conversation_thread_state"] = thread_state

    return {
        "expired_seed_ids": expired_seed_ids,
        "expired_signal_ids": expired_signal_ids,
        "expired_count": len(expired_seed_ids) + len(expired_signal_ids),
        "remaining_seed_count": len(kept_seeds),
        "remaining_thread_signal_count": len(kept_thread_signals),
        "remaining_rumor_signal_count": len(kept_rumor_signals),
        "seed_expiration": {
            "expired_seed_ids": expired_seed_ids,
            "remaining_count": len(kept_seeds),
            "current_tick": now,
        },
        "source": "deterministic_conversation_rumor_expiration",
    }


def maybe_seed_rumor_from_signal(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any] | None = None,
    *,
    signal: Dict[str, Any],
    topic_id: str = "",
    location_id: str = "",
    signal_kind: str = "",
    tick: int,
    settings: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    signal = _safe_dict(signal)
    # Allow callers to omit topic_id/location_id/signal_kind when they are in the signal dict
    topic_id = _safe_str(topic_id or signal.get("topic_id") or signal.get("source_topic_id"))
    location_id = _safe_str(location_id or signal.get("location_id"))
    signal_kind = _safe_str(signal_kind or signal.get("kind") or signal.get("signal_kind"))
    state = ensure_conversation_rumor_state(simulation_state)
    tombstone_key = _seed_key(topic_id=topic_id, location_id=location_id, signal_kind=signal_kind)
    tombstones = _safe_dict(state.get("expired_seed_tombstones"))
    if _safe_int(tombstones.get(tombstone_key), -1) == int(tick or 0):
        return {
            "created": False,
            "reason": "rumor_seed_expired_this_tick",
            "tombstone_key": tombstone_key,
        }
    seeds = _safe_list(state.get("rumor_seeds"))
    signal_id = _safe_str(signal.get("signal_id"))
    seed_key = _seed_key_from_parts(topic_id=topic_id, location_id=location_id, signal_kind=signal_kind)
    for existing in seeds:
        existing = _safe_dict(existing)
        if _safe_str(existing.get("source_signal_id")) == signal_id and signal_id:
            return {"created": False, "reason": "rumor_seed_already_exists", "rumor_seed": deepcopy(existing)}
        if _seed_key_from_seed(existing) == seed_key:
            return {"created": False, "reason": "rumor_seed_topic_location_already_exists", "rumor_seed": deepcopy(existing)}
    # Create new seed
    seed = {
        "rumor_seed_id": _stable_id("rumor_seed", signal_id, topic_id, location_id, tick),
        "source_signal_id": signal_id,
        "source_topic_id": _safe_str(topic_id),
        "location_id": _safe_str(location_id),
        "signal_kind": _safe_str(signal_kind),
        "created_tick": int(tick or 0),
        "expires_tick": int(tick or 0) + max(1, _safe_int(settings.get("max_signal_age_ticks"), MAX_SIGNAL_AGE_TICKS_DEFAULT)),
        "last_mentioned_tick": 0,
    }

    seed_id = _safe_str(seed.get("rumor_seed_id") or seed.get("seed_id"))
    if runtime_state and _is_seed_tombstoned_this_tick(
        runtime_state,
        seed_id=seed_id,
        current_tick=tick,
    ):
        return {
            "created": False,
            "reason": "seed_tombstoned_this_tick",
            "seed_id": seed_id,
            "source": "deterministic_conversation_rumor_runtime",
        }

    # Also ensure the seed has an explicit expiry
    seed["expires_tick"] = int(tick or 0) + max(1, _safe_int(settings.get("max_rumor_seed_age_ticks"), 3))
    seeds.append(seed)
    state["rumor_seeds"] = seeds
    return {"created": True, "rumor_seed": deepcopy(seed)}