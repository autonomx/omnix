"""Runtime-facing integration report adapters for RPG Phase 17."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from app.rpg.integration_hardening import Phase16IntegrationInput, build_phase16_integration_report
from app.rpg.replay_contracts import ReplaySnapshot
from app.rpg.world_director import DirectorState, StoryArc
from app.rpg.world_packs import LoreEntry, ModOverlay, WorldPack

RUNTIME_INTEGRATION_SOURCE = "phase17_runtime_integration_report_v1"
_REQUIRED_STATE_KEYS = (
    "world",
    "player",
    "party",
    "npcs",
    "quests",
    "map",
    "inventory",
    "combat",
    "memory",
)


def build_turn_runtime_integration_report(
    turn_result: Mapping[str, object],
    *,
    turn_index: int,
    player_action: str,
    recent_narrations: Sequence[str] = (),
    valid_actions: Sequence[str] = (),
) -> dict[str, object]:
    """Build a report payload suitable for turn/debug/autoplay surfaces."""

    state = _mapping(turn_result.get("simulation_state") or turn_result.get("state"))
    narration_payload = _mapping(turn_result.get("narration_payload"))
    narration = str(turn_result.get("narration") or narration_payload.get("text") or "")
    snapshot = ReplaySnapshot(
        f"runtime-turn-{turn_index}",
        int(turn_index),
        _seed(turn_result, state),
        counters=_counters(turn_result, state, turn_index),
        state=state,
    )
    report = build_phase16_integration_report(
        Phase16IntegrationInput(
            narration=narration,
            action_kind=_action_kind(turn_result, player_action),
            state_facts=_state_facts(turn_result, state),
            recent_texts=tuple(recent_narrations)[-5:],
            snapshot=snapshot,
            world_pack=_world_pack(turn_result, state),
            director_state=_director_state(turn_result, state, player_action),
            valid_actions=tuple(valid_actions) or _valid_actions(turn_result, player_action),
        )
    ).as_dict()
    issues = tuple(str(item) for item in report.get("readiness_issues") or ())
    return {
        "source": RUNTIME_INTEGRATION_SOURCE,
        "turn_index": int(turn_index),
        "player_action": player_action,
        "ready": not issues,
        "issues": list(issues),
        "state_groups_present": [key for key in _REQUIRED_STATE_KEYS if key in state],
        "phase16_report": report,
    }


def attach_runtime_integration_to_row(
    row: Mapping[str, object],
    *,
    previous_rows: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Return a transcript row decorated with a deterministic integration report."""

    result = dict(row)
    turn_result = _mapping(row.get("turn_result"))
    player_action = str(row.get("player_action") or turn_result.get("autoplay_action_text") or "")
    turn_index = int(row.get("turn_index") or turn_result.get("turn_index") or 0)
    recent = tuple(str(item.get("narration") or "") for item in previous_rows if isinstance(item, Mapping))
    report = build_turn_runtime_integration_report(
        turn_result,
        turn_index=turn_index,
        player_action=player_action,
        recent_narrations=recent,
        valid_actions=_row_valid_actions(row, turn_result, player_action),
    )
    result["runtime_integration_report"] = report
    return result


def attach_runtime_integration_to_autoplay_summary(
    summary: Mapping[str, object],
    *,
    persist: bool = False,
) -> dict[str, object]:
    """Attach Phase 17 integration reports to autoplay summary/transcript artifacts."""

    result = dict(summary)
    rows: list[dict[str, object]] = []
    raw_rows = summary.get("transcript_rows") or ()
    iterable_rows = raw_rows if _is_sequence(raw_rows) else ()
    for raw in iterable_rows:
        if not isinstance(raw, Mapping):
            continue
        rows.append(attach_runtime_integration_to_row(raw, previous_rows=rows))
    result["transcript_rows"] = rows
    result["runtime_integration"] = _aggregate_reports(rows)
    if persist:
        _persist_summary_artifacts(result)
    return result


def _aggregate_reports(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    issues: dict[str, int] = {}
    ready_count = 0
    for row in rows:
        report = _mapping(row.get("runtime_integration_report"))
        if report.get("ready") is True:
            ready_count += 1
        for issue in report.get("issues") or ():
            issues[str(issue)] = issues.get(str(issue), 0) + 1
    return {
        "source": RUNTIME_INTEGRATION_SOURCE,
        "turn_count": len(rows),
        "ready_turn_count": ready_count,
        "issue_counts": dict(sorted(issues.items())),
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _state_facts(turn_result: Mapping[str, object], state: Mapping[str, object]) -> Mapping[str, object]:
    facts = _mapping(turn_result.get("state_facts"))
    if facts:
        return facts
    return {key: state[key] for key in _REQUIRED_STATE_KEYS if key in state}


def _seed(turn_result: Mapping[str, object], state: Mapping[str, object]) -> int:
    for value in (turn_result.get("seed"), state.get("seed"), state.get("rng_seed")):
        if isinstance(value, int):
            return value
    return 0


def _counters(turn_result: Mapping[str, object], state: Mapping[str, object], turn_index: int) -> Mapping[str, int]:
    for raw in (turn_result.get("counters"), state.get("counters"), state.get("rng_counters")):
        if isinstance(raw, Mapping):
            counters = {str(key): int(value) for key, value in raw.items() if isinstance(value, int)}
            if counters:
                return counters
    return {"turn_index": int(turn_index)}


def _action_kind(turn_result: Mapping[str, object], player_action: str) -> str:
    for key in ("action_kind", "action_category", "validated_presentation_category"):
        value = turn_result.get(key)
        if value:
            return str(value)
    return player_action.split(" ", 1)[0].lower() if player_action else "general"


def _world_pack(turn_result: Mapping[str, object], state: Mapping[str, object]) -> WorldPack:
    raw = _mapping(turn_result.get("world_pack") or state.get("world_pack"))
    overlays = tuple(_overlay(item) for item in _sequence(raw.get("overlays")) if isinstance(item, Mapping))
    lore = tuple(_lore(item) for item in _sequence(raw.get("lore")) if isinstance(item, Mapping))
    return WorldPack(
        str(raw.get("pack_id") or "runtime"),
        str(raw.get("title") or "Runtime World"),
        regions=tuple(str(item) for item in _sequence(raw.get("regions"))) or ("runtime",),
        lore=lore,
        overlays=overlays,
    )


def _director_state(turn_result: Mapping[str, object], state: Mapping[str, object], player_action: str) -> DirectorState:
    raw = _mapping(turn_result.get("director_state") or state.get("director_state"))
    arcs = tuple(_arc(item) for item in _sequence(raw.get("arcs")) if isinstance(item, Mapping))
    recent_actions = tuple(str(item) for item in _sequence(raw.get("recent_actions")))
    return DirectorState(
        arcs=arcs,
        recent_locations=tuple(str(item) for item in _sequence(raw.get("recent_locations")))[-5:],
        recent_npcs=tuple(str(item) for item in _sequence(raw.get("recent_npcs")))[-5:],
        recent_actions=(recent_actions + (player_action,))[-5:],
        danger_level=int(raw.get("danger_level") or 0),
        downtime=int(raw.get("downtime") or 0),
    )


def _valid_actions(turn_result: Mapping[str, object], player_action: str) -> tuple[str, ...]:
    raw_actions = turn_result.get("valid_actions") or turn_result.get("suggested_actions")
    actions = tuple(str(item) for item in _sequence(raw_actions))
    return actions or ((player_action,) if player_action else ())


def _row_valid_actions(row: Mapping[str, object], turn_result: Mapping[str, object], player_action: str) -> tuple[str, ...]:
    return tuple(str(item) for item in _sequence(row.get("valid_actions"))) or _valid_actions(turn_result, player_action)


def _sequence(value: object) -> tuple[object, ...]:
    return tuple(value) if _is_sequence(value) else ()


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _overlay(raw: Mapping[str, object]) -> ModOverlay:
    return ModOverlay(
        str(raw.get("overlay_id") or "runtime-overlay"),
        str(raw.get("kind") or "item"),
        _mapping(raw.get("payload")),
    )


def _lore(raw: Mapping[str, object]) -> LoreEntry:
    return LoreEntry(
        str(raw.get("key") or "runtime"),
        str(raw.get("title") or "Runtime"),
        str(raw.get("body") or "Runtime lore."),
        str(raw.get("scope") or "world"),
    )


def _arc(raw: Mapping[str, object]) -> StoryArc:
    return StoryArc(
        str(raw.get("arc_id") or "runtime-arc"),
        str(raw.get("title") or "Runtime Arc"),
        threat=str(raw.get("threat") or ""),
    )


def _persist_summary_artifacts(summary: Mapping[str, object]) -> None:
    paths = _mapping(summary.get("artifact_paths"))
    for key in ("summary", "transcript"):
        path = paths.get(key)
        if not path:
            continue
        payload: object = summary if key == "summary" else summary.get("transcript_rows", [])
        Path(str(path)).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
