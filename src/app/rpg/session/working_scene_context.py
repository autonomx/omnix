from __future__ import annotations

from typing import Any, Mapping, Sequence

WORKING_SCENE_CONTEXT_VERSION = "working_scene_context_v1"
DEFAULT_WORKING_CONTEXT_TOKEN_BUDGET = 3000


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def estimate_context_tokens(text: str) -> int:
    """Cheap deterministic token estimate for prompt-budget enforcement."""

    return max(1, (len(text) + 3) // 4) if text.strip() else 0


def _short(value: Any, limit: int = 180) -> str:
    text = " ".join(_text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _player_block(session: Mapping[str, Any]) -> dict[str, Any]:
    state = _dict(session.get("state"))
    simulation = _dict(session.get("simulation_state"))
    player = _dict(_dict(simulation.get("player_state")) or state.get("player"))
    currency = _dict(player.get("currency"))
    location = _text(player.get("location") or state.get("location") or simulation.get("current_location"))
    inventory_state = _dict(player.get("inventory_state"))
    items = _list(inventory_state.get("items")) or _list(player.get("inventory"))
    return {
        "name": _text(player.get("name") or state.get("player_name") or "Player"),
        "level": player.get("level") or player.get("character_level") or 1,
        "xp": player.get("xp") or player.get("experience") or 0,
        "location": location,
        "currency": currency,
        "inventory": [_short(_dict(item).get("name") or _dict(item).get("item_id") or item, 60) for item in items[:8]],
    }


def _scene_block(session: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _dict(session.get("manifest"))
    state = _dict(session.get("state"))
    simulation = _dict(session.get("simulation_state"))
    runtime = _dict(session.get("runtime_state"))
    return {
        "session_id": _text(manifest.get("session_id") or manifest.get("id") or session.get("id")),
        "location": _text(
            runtime.get("location")
            or simulation.get("current_location")
            or state.get("location")
            or state.get("current_location")
        ),
        "time": _text(state.get("time") or runtime.get("time") or simulation.get("time")),
        "mood": _short(runtime.get("scene_mood") or state.get("scene_mood") or simulation.get("scene_mood"), 120),
    }


def _visible_npc_block(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = _dict(session.get("runtime_state"))
    state = _dict(session.get("state"))
    simulation = _dict(session.get("simulation_state"))
    candidates: list[Any] = []
    for source in (
        runtime.get("visible_npcs"),
        simulation.get("visible_npcs"),
        state.get("visible_npcs"),
        state.get("npcs"),
        simulation.get("npcs"),
    ):
        if isinstance(source, Mapping):
            candidates.extend(source.values())
        else:
            candidates.extend(_list(source))
    seen: set[str] = set()
    npcs: list[dict[str, Any]] = []
    for candidate in candidates:
        npc = _dict(candidate)
        name = _text(npc.get("name") or npc.get("id"))
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        npcs.append(
            {
                "id": _text(npc.get("id")),
                "name": name,
                "role": _short(npc.get("role") or npc.get("occupation") or npc.get("title"), 80),
                "disposition": _short(npc.get("disposition") or npc.get("mood") or npc.get("relationship"), 80),
            }
        )
        if len(npcs) >= 8:
            break
    return npcs


def _quest_block(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    state = _dict(session.get("state"))
    runtime = _dict(session.get("runtime_state"))
    candidates = _list(state.get("quests")) or _list(runtime.get("quests")) or _list(state.get("journal"))
    quests: list[dict[str, Any]] = []
    for quest in candidates[:6]:
        item = _dict(quest)
        quests.append(
            {
                "title": _short(item.get("title") or item.get("name") or item.get("id") or quest, 90),
                "status": _short(item.get("status") or item.get("state"), 40),
                "next": _short(item.get("next") or item.get("next_step") or item.get("objective"), 120),
            }
        )
    return quests


def _recent_block(session: Mapping[str, Any]) -> list[str]:
    runtime = _dict(session.get("runtime_state"))
    state = _dict(session.get("state"))
    candidates = _list(runtime.get("recent_turns")) or _list(state.get("recent_turns")) or _list(session.get("timeline"))
    recent: list[str] = []
    for event in candidates[-6:]:
        if isinstance(event, Mapping):
            text = event.get("summary") or event.get("text") or event.get("content") or event.get("command")
        else:
            text = event
        line = _short(text, 160)
        if line:
            recent.append(line)
    return recent


def render_working_scene_context(context: Mapping[str, Any]) -> str:
    """Render a compact prompt-facing context capsule."""

    blocks = _dict(context.get("blocks"))
    lines = ["WORKING SCENE CONTEXT", f"Version: {context.get('format_version')}"]
    scene = _dict(blocks.get("scene"))
    if scene:
        lines.append(f"Scene: {scene.get('location') or 'unknown'} | {scene.get('time') or 'time unknown'}")
    player = _dict(blocks.get("player"))
    if player:
        lines.append(f"Player: {player.get('name')} | level {player.get('level')} | location {player.get('location') or scene.get('location') or 'unknown'}")
    npcs = _list(blocks.get("visible_npcs"))
    if npcs:
        lines.append("Visible NPCs: " + "; ".join(_text(_dict(npc).get("name")) for npc in npcs if _text(_dict(npc).get("name"))))
    quests = _list(blocks.get("quests"))
    if quests:
        lines.append("Active objectives: " + "; ".join(_short(_dict(q).get("next") or _dict(q).get("title"), 120) for q in quests))
    recent = _list(blocks.get("recent"))
    if recent:
        lines.append("Recent turns: " + " / ".join(_short(item, 140) for item in recent))
    mechanics = _list(blocks.get("mechanics"))
    if mechanics:
        lines.append("Allowed mechanics: " + ", ".join(_text(item) for item in mechanics if _text(item)))
    player_input = _text(context.get("player_input"))
    if player_input:
        lines.append(f"Current player input: {player_input}")
    return "\n".join(line for line in lines if line.strip()).strip()


def build_working_scene_context(
    session: Mapping[str, Any],
    *,
    player_input: str = "",
    max_tokens: int = DEFAULT_WORKING_CONTEXT_TOKEN_BUDGET,
    mechanics: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the compact context capsule used by fast player-facing turns."""

    budget = max(500, min(12000, int(max_tokens or DEFAULT_WORKING_CONTEXT_TOKEN_BUDGET)))
    blocks = {
        "scene": _scene_block(session),
        "player": _player_block(session),
        "visible_npcs": _visible_npc_block(session),
        "quests": _quest_block(session),
        "recent": _recent_block(session),
        "mechanics": list(mechanics or ("dialogue", "service", "travel", "investigation", "combat")),
    }
    context = {
        "format_version": WORKING_SCENE_CONTEXT_VERSION,
        "player_input": _short(player_input, 300),
        "max_tokens": budget,
        "blocks": blocks,
    }
    compact = render_working_scene_context(context)
    while estimate_context_tokens(compact) > budget and blocks["recent"]:
        blocks["recent"] = blocks["recent"][1:]
        compact = render_working_scene_context(context)
    context["compact_text"] = compact
    context["estimated_tokens"] = estimate_context_tokens(compact)
    return context
