from __future__ import annotations

from app.runtime.clock import utc_now

# RPG session runtime responsibility module.
from app.apps.rpg.session.state_normalization import (
    _safe_dict as _safe_dict,
    _safe_int as _safe_int,
    _safe_list as _safe_list,
    _safe_str as _safe_str,
)
from app.apps.rpg.session.companion_turn_runtime import (
    _MAX_LOCATION_CONDITIONS as _MAX_LOCATION_CONDITIONS, _MAX_RECENT_SCENE_BEATS as _MAX_RECENT_SCENE_BEATS, _MAX_RECENT_WORLD_EVENT_ROWS as _MAX_RECENT_WORLD_EVENT_ROWS,
    _MAX_WORLD_CONSEQUENCES as _MAX_WORLD_CONSEQUENCES, _MAX_WORLD_PRESSURE as _MAX_WORLD_PRESSURE, _MAX_WORLD_RUMORS as _MAX_WORLD_RUMORS,
)
import hashlib as hashlib
import json as json
from app.apps.rpg.rules.economy.menu_catalog import (
    build_available_transaction_menus as build_available_transaction_menus, build_provider_transaction_menus as build_provider_transaction_menus,
)
from app.apps.rpg.rules.economy.provider_catalog import (
    derive_npc_transaction_providers as derive_npc_transaction_providers, derive_world_transaction_providers as derive_world_transaction_providers,
)
from datetime import (
    datetime as datetime, timezone as timezone,
)
from typing import (
    Any as Any, Dict as Dict, List as List,
)


_CRITICAL_REACTION_KINDS = frozenset({"follow_reaction", "caution_reaction", "assist_reaction", "warning"})


def _seconds_since_iso(iso_str: str, *, now: datetime | None = None) -> int:
    """Return seconds elapsed since an ISO timestamp. Returns 9999 if invalid."""
    iso_str = _safe_str(iso_str).strip()
    if not iso_str:
        return 9999
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = (now or utc_now()) - dt
        return max(0, int(delta.total_seconds()))
    except Exception:
        return 9999


def _derive_transaction_context_tags(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[str]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    tags: list[str] = []
    seen = set()

    def _add(value: Any) -> None:
        text = _safe_str(value).strip().lower()
        if text and text not in seen:
            seen.add(text)
            tags.append(text)

    current_scene = _safe_dict(runtime_state.get("current_scene"))
    scene_tags = _safe_list(current_scene.get("tags"))
    for tag in scene_tags:
        _add(tag)

    for npc in _safe_list(runtime_state.get("npcs"))[:24]:
        npc = _safe_dict(npc)
        role = _safe_str(npc.get("role")).lower()
        profession = _safe_str(npc.get("profession")).lower()
        location_type = _safe_str(npc.get("location_type")).lower()
        _add(role)
        _add(profession)
        _add(location_type)

    scene_kind = _safe_str(current_scene.get("scene_type")).lower()
    _add(scene_kind)

    return tags[:16]


def _derive_transaction_providers(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = _safe_dict(runtime_state)

    npcs = _safe_list(runtime_state.get("npcs"))
    world_entities = _safe_list(runtime_state.get("world_entities"))

    npc_providers = derive_npc_transaction_providers(npcs)
    world_providers = derive_world_transaction_providers(world_entities)

    combined: list[dict[str, Any]] = []
    seen = set()

    for provider in npc_providers + world_providers:
        provider = _safe_dict(provider)
        provider_id = _safe_str(provider.get("provider_id"))
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        combined.append(provider)

    return combined[:24]


def _build_transaction_menus_for_state(
    simulation_state: dict[str, Any],
    runtime_state: dict[str, Any],
) -> list[dict[str, Any]]:
    providers = _derive_transaction_providers(simulation_state, runtime_state)
    menus = build_provider_transaction_menus(providers)
    if menus:
        return menus

    # Backward-compatible fallback while world/NPC data matures.
    transaction_context_tags = _derive_transaction_context_tags(simulation_state, runtime_state)
    return build_available_transaction_menus(transaction_context_tags)


def _stable_scene_beat_id(beat: dict[str, Any]) -> str:
    payload = {
        "tick": int(_safe_dict(beat).get("tick", 0) or 0),
        "kind": _safe_str(_safe_dict(beat).get("kind")),
        "summary": _safe_str(_safe_dict(beat).get("summary")),
        "scene_id": _safe_str(_safe_dict(beat).get("scene_id")),
        "interaction_id": _safe_str(_safe_dict(beat).get("interaction_id")),
        "actors": sorted([_safe_str(x) for x in _safe_list(_safe_dict(beat).get("actors")) if _safe_str(x)]),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return "scene_beat_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_scene_beat(beat: dict[str, Any]) -> dict[str, Any]:
    beat = _safe_dict(beat)
    out = {
        "id": _safe_str(beat.get("id")),
        "tick": int(beat.get("tick", 0) or 0),
        "kind": _safe_str(beat.get("kind")) or "scene_beat",
        "summary": _safe_str(beat.get("summary")),
        "priority": int(beat.get("priority", 50) or 50),
        "scene_id": _safe_str(beat.get("scene_id")),
        "interaction_id": _safe_str(beat.get("interaction_id")),
        "actors": [_safe_str(x) for x in _safe_list(beat.get("actors")) if _safe_str(x)],
        "location_id": _safe_str(beat.get("location_id")),
        "recap_level": _safe_str(beat.get("recap_level")) or "notable",
        "tags": [_safe_str(x) for x in _safe_list(beat.get("tags")) if _safe_str(x)],
    }
    if not out["id"]:
        out["id"] = _stable_scene_beat_id(out)
    return out


def _ensure_recent_scene_beats(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    beats = []
    seen = set()
    for beat in _safe_list(runtime_state.get("recent_scene_beats")):
        norm = _normalize_scene_beat(beat)
        if not norm["summary"]:
            continue
        if norm["id"] in seen:
            continue
        seen.add(norm["id"])
        beats.append(norm)
    beats.sort(key=lambda item: (int(item.get("tick", 0)), int(item.get("priority", 0)), _safe_str(item.get("id"))))
    runtime_state["recent_scene_beats"] = beats[-_MAX_RECENT_SCENE_BEATS:]
    return runtime_state


# ── World consequence state ──────────────────────────────────────────────────

def _stable_consequence_id(prefix: str, tick: int, scope: str, key: str, summary: str) -> str:
    # For mergeable consequences, use content-based ID, not tick-based
    if prefix in ("rumor", "pressure", "condition", "consequence"):
        raw = f"{prefix}|{scope}|{key}|{summary}"
    else:
        raw = f"{prefix}|{tick}|{scope}|{key}|{summary}"
    return prefix + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_world_rumor(record: dict[str, Any]) -> dict[str, Any]:
    record = _safe_dict(record)
    return {
        "rumor_id": _safe_str(record.get("rumor_id")),
        "summary": _safe_str(record.get("summary")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "source_actor_id": _safe_str(record.get("source_actor_id")),
        "source_kind": _safe_str(record.get("source_kind")),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "strength": max(1, _safe_int(record.get("strength"), 1)),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_pressure_record(record: dict[str, Any]) -> dict[str, Any]:
    record = _safe_dict(record)
    return {
        "pressure_id": _safe_str(record.get("pressure_id")),
        "kind": _safe_str(record.get("kind")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "value": max(0, _safe_int(record.get("value"), 0)),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "summary": _safe_str(record.get("summary")),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_location_condition(record: dict[str, Any]) -> dict[str, Any]:
    record = _safe_dict(record)
    return {
        "condition_id": _safe_str(record.get("condition_id")),
        "location_id": _safe_str(record.get("location_id")),
        "kind": _safe_str(record.get("kind")),
        "summary": _safe_str(record.get("summary")),
        "severity": max(1, _safe_int(record.get("severity"), 1)),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "status": _safe_str(record.get("status")) or "active",
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_world_consequence(record: dict[str, Any]) -> dict[str, Any]:
    record = _safe_dict(record)
    return {
        "consequence_id": _safe_str(record.get("consequence_id")),
        "kind": _safe_str(record.get("kind")),
        "scope": _safe_str(record.get("scope")) or "local",
        "location_id": _safe_str(record.get("location_id")),
        "summary": _safe_str(record.get("summary")),
        "source_actor_id": _safe_str(record.get("source_actor_id")),
        "source_activity_id": _safe_str(record.get("source_activity_id")),
        "tick": _safe_int(record.get("tick"), 0),
        "priority": max(1, _safe_int(record.get("priority"), 1)),
        "tags": [str(x).strip() for x in _safe_list(record.get("tags")) if str(x).strip()],
    }


def _normalize_consequence_text(text: str) -> str:
    text = _safe_str(text).lower()
    text = " ".join(text.split())
    text = text.rstrip(".,!?;:")
    return text


def _world_rumor_key(record: dict[str, Any]) -> str:
    record = _normalize_world_rumor(record)
    return "|".join([
        _safe_str(record.get("scope")),
        _safe_str(record.get("location_id")),
        _normalize_consequence_text(_safe_str(record.get("summary"))),
        _safe_str(record.get("source_kind")),
    ])


def _world_pressure_key(record: dict[str, Any]) -> str:
    record = _normalize_pressure_record(record)
    return "|".join([
        _safe_str(record.get("scope")),
        _safe_str(record.get("location_id")),
        _safe_str(record.get("kind")),
    ])


def _location_condition_key(record: dict[str, Any]) -> str:
    record = _normalize_location_condition(record)
    return "|".join([
        _safe_str(record.get("location_id")),
        _safe_str(record.get("kind")),
    ])


def _world_consequence_key(record: dict[str, Any]) -> str:
    record = _normalize_world_consequence(record)
    return "|".join([
        _safe_str(record.get("scope")),
        _safe_str(record.get("location_id")),
        _safe_str(record.get("kind")),
        _normalize_consequence_text(_safe_str(record.get("summary"))),
    ])


def ensure_world_consequence_state(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)

    rumors = [_normalize_world_rumor(x) for x in _safe_list(runtime_state.get("world_rumors"))]
    pressures = [_normalize_pressure_record(x) for x in _safe_list(runtime_state.get("world_pressure"))]
    conditions = [_normalize_location_condition(x) for x in _safe_list(runtime_state.get("location_conditions"))]
    consequences = [_normalize_world_consequence(x) for x in _safe_list(runtime_state.get("world_consequences"))]

    runtime_state["world_rumors"] = rumors[-_MAX_WORLD_RUMORS:]
    runtime_state["world_pressure"] = pressures[-_MAX_WORLD_PRESSURE:]
    runtime_state["location_conditions"] = conditions[-_MAX_LOCATION_CONDITIONS:]
    runtime_state["world_consequences"] = consequences[-_MAX_WORLD_CONSEQUENCES:]
    return runtime_state


# ── Active NPC activity state ────────────────────────────────────────────────

_MAX_ACTIVE_ACTIVITIES = 64


def _stable_activity_id(actor_id: str, tick: int, kind: str, location_id: str, target_id: str = "") -> str:
    actor_id = _safe_str(actor_id)
    kind = _safe_str(kind)
    location_id = _safe_str(location_id)
    target_id = _safe_str(target_id)
    raw = f"{actor_id}|{tick}|{kind}|{location_id}|{target_id}"
    return "activity_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _normalize_activity_record(record: dict[str, Any]) -> dict[str, Any]:
    record = _safe_dict(record)
    return {
        "activity_id": _safe_str(record.get("activity_id")),
        "kind": _safe_str(record.get("kind")),
        "summary": _safe_str(record.get("summary")),
        "location_id": _safe_str(record.get("location_id")),
        "target_id": _safe_str(record.get("target_id")),
        "target_label": _safe_str(record.get("target_label")),
        "started_tick": _safe_int(record.get("started_tick"), 0),
        "updated_tick": _safe_int(record.get("updated_tick"), 0),
        "expected_duration": max(1, _safe_int(record.get("expected_duration"), 1)),
        "status": _safe_str(record.get("status")) or "active",
        "intent": _safe_str(record.get("intent")),
        "world_tags": [str(x).strip() for x in _safe_list(record.get("world_tags")) if str(x).strip()],
    }


def ensure_actor_activity_state(runtime_state: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _safe_dict(runtime_state)
    actor_activities = _safe_dict(runtime_state.get("actor_activities"))
    normalized: dict[str, Any] = {}
    for actor_id, rec in actor_activities.items():
        actor_id = _safe_str(actor_id)
        if not actor_id:
            continue
        normalized[actor_id] = _normalize_activity_record(rec)
    runtime_state["actor_activities"] = normalized
    return runtime_state


def get_actor_activity(runtime_state: dict[str, Any], actor_id: str) -> dict[str, Any]:
    runtime_state = ensure_actor_activity_state(runtime_state)
    return _safe_dict(_safe_dict(runtime_state.get("actor_activities")).get(_safe_str(actor_id)))


def set_actor_activity(runtime_state: dict[str, Any], actor_id: str, activity: dict[str, Any]) -> dict[str, Any]:
    runtime_state = ensure_actor_activity_state(runtime_state)
    actor_id = _safe_str(actor_id)
    if not actor_id:
        return runtime_state
    actor_activities = _safe_dict(runtime_state.get("actor_activities"))
    actor_activities[actor_id] = _normalize_activity_record(activity)
    # bounded by actor count naturally, but normalize anyway
    runtime_state["actor_activities"] = dict(list(actor_activities.items())[-_MAX_ACTIVE_ACTIVITIES:])
    return runtime_state


# ── Living world activity planner ────────────────────────────────────────────

_LOCAL_ACTIVITY_KINDS = (
    "patrol",
    "watch_crowd",
    "trade",
    "gossip",
    "serve",
    "clean",
    "rest",
    "question_patron",
)


def _sorted_npc_entities(simulation_state: dict[str, Any]) -> list[dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    out: list[dict[str, Any]] = []

    npc_index = _safe_dict(simulation_state.get("npc_index"))
    for npc_id, npc in npc_index.items():
        npc = _safe_dict(npc)
        rec = dict(npc)
        if not _safe_str(rec.get("id")):
            rec["id"] = _safe_str(npc_id)
        out.append(rec)

    if not out:
        for npc in _safe_list(simulation_state.get("npcs")):
            npc = _safe_dict(npc)
            if _safe_str(npc.get("id")):
                out.append(npc)

    out.sort(key=lambda x: (_safe_str(x.get("location_id")), _safe_str(x.get("name")), _safe_str(x.get("id"))))
    return out


def _choose_activity_kind_for_actor(actor: dict[str, Any], tick: int, runtime_state: dict[str, Any] | None = None) -> str:
    actor = _safe_dict(actor)
    runtime_state = ensure_world_consequence_state(_safe_dict(runtime_state))
    actor_id = _safe_str(actor.get("id"))
    name = _safe_str(actor.get("name"))
    location_id = _safe_str(actor.get("location_id")) or _safe_str(actor.get("current_location_id"))

    # Feedback bias from local conditions / pressure / rumors
    local_pressure = 0
    for p in _safe_list(runtime_state.get("world_pressure")):
        p = _normalize_pressure_record(p)
        if _safe_str(p.get("location_id")) == location_id and _safe_str(p.get("kind")) == "security_presence":
            local_pressure += _safe_int(p.get("value"), 0)

    local_rumors = 0
    for r in _safe_list(runtime_state.get("world_rumors")):
        r = _normalize_world_rumor(r)
        if _safe_str(r.get("location_id")) == location_id:
            local_rumors += _safe_int(r.get("strength"), 0)

    if local_pressure >= 3:
        # High pressure: bias heavily toward security activities
        options: tuple[str, ...] = ("patrol", "watch_crowd", "question_patron", "patrol", "watch_crowd", "serve", "clean")
    elif local_pressure >= 2:
        # Medium pressure: bias toward security but allow variety
        options = ("patrol", "watch_crowd", "trade", "serve", "clean", "gossip", "question_patron")
    elif local_rumors >= 3:
        # High rumors: bias toward social activities
        options = ("gossip", "gossip", "trade", "serve", "watch_crowd")
    elif local_rumors >= 2:
        # Medium rumors: bias toward social but allow variety
        options = ("gossip", "trade", "serve", "watch_crowd", "clean", "patrol")
    else:
        options = _LOCAL_ACTIVITY_KINDS

    seed = f"{actor_id}|{name}|{tick}|{location_id}|{local_pressure}|{local_rumors}"
    idx = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8], 16) % len(options)
    return options[idx]


def _build_activity_summary(actor: dict[str, Any], kind: str) -> str:
    actor = _safe_dict(actor)
    actor_name = _safe_str(actor.get("name")) or _safe_str(actor.get("id")) or "Someone"
    if kind == "patrol":
        return f"{actor_name} patrols nearby, watching for trouble."
    if kind == "watch_crowd":
        return f"{actor_name} keeps a close eye on the crowd."
    if kind == "trade":
        return f"{actor_name} haggles over goods and prices."
    if kind == "gossip":
        return f"{actor_name} trades rumors with the locals."
    if kind == "serve":
        return f"{actor_name} serves people and keeps things moving."
    if kind == "clean":
        return f"{actor_name} tidies up and keeps the place in order."
    if kind == "rest":
        return f"{actor_name} takes a quiet moment to rest and observe."
    if kind == "question_patron":
        return f"{actor_name} questions someone about suspicious behavior."
    return f"{actor_name} is busy with local matters."


def _build_activity_intent(kind: str) -> str:
    if kind in ("patrol", "watch_crowd", "question_patron"):
        return "Maintain order and watch for trouble."
    if kind == "trade":
        return "Make a profitable exchange."
    if kind == "gossip":
        return "Learn and spread useful rumors."
    if kind == "serve":
        return "Keep customers attended to."
    if kind == "clean":
        return "Keep the area in good condition."
    if kind == "rest":
        return "Recover while staying aware."
    return "Pursue current routine."


def _build_activity_tags(kind: str) -> list[str]:
    if kind in ("patrol", "watch_crowd", "question_patron"):
        return ["security", "local"]
    if kind == "trade":
        return ["commerce", "local"]
    if kind == "gossip":
        return ["rumor", "social", "local"]
    if kind == "serve":
        return ["service", "local"]
    if kind == "clean":
        return ["maintenance", "local"]
    if kind == "rest":
        return ["idle", "local"]
    return ["local"]


def advance_actor_activities_for_tick(simulation_state: dict[str, Any], runtime_state: dict[str, Any]) -> dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_actor_activity_state(runtime_state)
    tick = _safe_int(simulation_state.get("tick"), 0)
    npcs = _sorted_npc_entities(simulation_state)
    if not npcs:
        return runtime_state

    # bounded deterministic rotation
    start = tick % len(npcs)
    selected = []
    for offset in range(min(3, len(npcs))):
        selected.append(npcs[(start + offset) % len(npcs)])

    for actor in selected:
        actor_id = _safe_str(actor.get("id"))
        if not actor_id:
            continue
        current = get_actor_activity(runtime_state, actor_id)
        location_id = _safe_str(actor.get("location_id")) or _safe_str(actor.get("current_location_id"))
        if current and _safe_str(current.get("status")) == "active":
            age = tick - _safe_int(current.get("started_tick"), tick)
            duration = _safe_int(current.get("expected_duration"), 1)
            if age < duration:
                current["updated_tick"] = tick
                runtime_state = set_actor_activity(runtime_state, actor_id, current)
                continue

        kind = _choose_activity_kind_for_actor(actor, tick, runtime_state)
        activity = {
            "activity_id": _stable_activity_id(actor_id, tick, kind, location_id),
            "kind": kind,
            "summary": _build_activity_summary(actor, kind),
            "location_id": location_id,
            "target_id": "",
            "target_label": "",
            "started_tick": tick,
            "updated_tick": tick,
            "expected_duration": 2 + (tick % 3),
            "status": "active",
            "intent": _build_activity_intent(kind),
            "world_tags": _build_activity_tags(kind),
        }
        runtime_state = set_actor_activity(runtime_state, actor_id, activity)

    return runtime_state


# ── Activity beats ──────────────────────────────────────────────────────────

_MAX_ACTIVITY_SCENE_BEATS = 64
_MAX_GLOBAL_WORLD_BEATS = 64


def _stable_world_beat_id(prefix: str, actor_id: str, tick: int, summary: str) -> str:
    raw = f"{prefix}|{actor_id}|{tick}|{summary}"
    return prefix + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def emit_activity_beats_for_tick(simulation_state: dict[str, Any], runtime_state: dict[str, Any]) -> dict[str, Any]:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = ensure_actor_activity_state(runtime_state)
    tick = _safe_int(simulation_state.get("tick"), 0)

    recent_scene_beats = _safe_list(runtime_state.get("recent_scene_beats"))
    recent_world_event_rows = _safe_list(runtime_state.get("recent_world_event_rows"))
    global_world_beats = _safe_list(runtime_state.get("global_world_beats"))

    actor_activities = _safe_dict(runtime_state.get("actor_activities"))
    for actor_id, activity in sorted(actor_activities.items()):
        activity = _normalize_activity_record(activity)
        if _safe_str(activity.get("status")) != "active":
            continue
        if _safe_int(activity.get("updated_tick"), 0) != tick:
            continue

        summary = _safe_str(activity.get("summary"))
        location_id = _safe_str(activity.get("location_id"))
        tags = _safe_list(activity.get("world_tags"))
        beat_id = _stable_world_beat_id("activity_beat", actor_id, tick, summary)

        scene_beat = {
            "beat_id": beat_id,
            "tick": tick,
            "kind": "activity_beat",
            "summary": summary,
            "location_id": location_id,
            "actor_id": actor_id,
            "priority": 40,
            "tags": tags,
        }
        recent_scene_beats.append(scene_beat)

        recent_world_event_rows.append({
            "event_id": beat_id,
            "scope": "local",
            "kind": "activity_beat",
            "title": "Local Activity",
            "summary": summary,
            "tick": tick,
            "actors": [actor_id],
            "actor_id": actor_id,
            "location_id": location_id,
            "priority": 0.7,
            "status": "active",
            "source": "activity_runtime",
        })

        # Some activity kinds also create broader world beats
        kind = _safe_str(activity.get("kind"))
        if kind in ("gossip", "trade", "question_patron", "patrol"):
            global_summary = ""
            if kind == "gossip":
                global_summary = "Rumors circulate more quickly through local taverns."
            elif kind == "trade":
                global_summary = "Trade activity shifts prices and availability in the area."
            elif kind == "question_patron":
                global_summary = "The local watch grows more alert after suspicious behavior."
            elif kind == "patrol":
                global_summary = "Watch presence remains noticeable in nearby streets."

            if global_summary:
                global_id = _stable_world_beat_id("global_beat", actor_id, tick, global_summary)
                global_world_beats.append({
                    "event_id": global_id,
                    "scope": "global",
                    "kind": "world_event",
                    "title": "World Event",
                    "summary": global_summary,
                    "tick": tick,
                    "actors": [actor_id],
                    "actor_id": actor_id,
                    "location_id": "",
                    "priority": 0.6,
                    "status": "active",
                    "source": "activity_runtime",
                })

    runtime_state["recent_scene_beats"] = recent_scene_beats[-_MAX_ACTIVITY_SCENE_BEATS:]
    runtime_state["recent_world_event_rows"] = recent_world_event_rows[-_MAX_RECENT_WORLD_EVENT_ROWS:]
    runtime_state["global_world_beats"] = global_world_beats[-_MAX_GLOBAL_WORLD_BEATS:]
    return runtime_state

__all__ = [
    "_LOCAL_ACTIVITY_KINDS",
    "_MAX_ACTIVE_ACTIVITIES",
    "_MAX_ACTIVITY_SCENE_BEATS",
    "_MAX_GLOBAL_WORLD_BEATS",
    "_MAX_RECENT_SCENE_BEATS",
    "_build_activity_intent",
    "_build_activity_summary",
    "_build_activity_tags",
    "_build_transaction_menus_for_state",
    "_choose_activity_kind_for_actor",
    "_derive_transaction_context_tags",
    "_derive_transaction_providers",
    "_ensure_recent_scene_beats",
    "_location_condition_key",
    "_normalize_activity_record",
    "_normalize_consequence_text",
    "_normalize_location_condition",
    "_normalize_pressure_record",
    "_normalize_scene_beat",
    "_normalize_world_consequence",
    "_normalize_world_rumor",
    "_seconds_since_iso",
    "_sorted_npc_entities",
    "_stable_activity_id",
    "_stable_consequence_id",
    "_stable_scene_beat_id",
    "_stable_world_beat_id",
    "_world_consequence_key",
    "_world_pressure_key",
    "_world_rumor_key",
    "advance_actor_activities_for_tick",
    "emit_activity_beats_for_tick",
    "ensure_actor_activity_state",
    "ensure_world_consequence_state",
    "get_actor_activity",
    "set_actor_activity",
]
