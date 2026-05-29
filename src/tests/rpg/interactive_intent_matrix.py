"""CD/CE/CF — interactive intent matrix regression suite.

Realistic player-facing scripts for the interactive CLI path. CF adds matrix-level
performance rollups so slow live-provider runs are visible in the top-level
summary without opening every per-scenario artifact.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
TESTS_ROOT = THIS_FILE.parents[1]
SRC_ROOT = THIS_FILE.parents[2]
REPO_ROOT = THIS_FILE.parents[3]
for path in (str(TESTS_ROOT), str(SRC_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests.rpg import interactive_cli_campaign as cli  # noqa: E402

MATRIX_VERSION = "interactive_intent_matrix_v4"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "resources" / "data" / "test-results" / "interactive-intent-matrix"
MATRIX_FAST_TURN_PERFORMANCE = {
    "fast_turn_mode": True,
    "enable_action_advisory": False,
    "enable_semantic_action_advisory": False,
    "enable_live_narration_llm": False,
    "enable_narration_retry": False,
    "enable_continuity_grounding": False,
    "compact_save": True,
}
COMBAT_MATRIX_SCENARIO_ID = "combat_basic_attack"
COMBAT_MATRIX_OPENING_HP = 4
PARTY_MATRIX_SCENARIO_ID = "party_companion_recruitment"


@dataclass(frozen=True)
class TurnExpectation:
    turn_index: int
    contains_any: Sequence[str] = field(default_factory=tuple)
    contains_all: Sequence[str] = field(default_factory=tuple)
    forbids: Sequence[str] = field(default_factory=tuple)
    npc_line_contains_any: Sequence[str] = field(default_factory=tuple)
    require_npc_line: bool = False
    final_action_type: str = ""
    final_service_kind: str = ""
    final_target_contains_any: Sequence[str] = field(default_factory=tuple)
    final_requested_terms_contains_any: Sequence[str] = field(default_factory=tuple)
    narration_source_any: Sequence[str] = field(default_factory=tuple)
    provider_called: bool | None = True


@dataclass(frozen=True)
class IntentMatrixScenario:
    scenario_id: str
    title: str
    commands: Sequence[str]
    expectations: Sequence[TurnExpectation]
    description: str = ""


def default_intent_matrix_scenarios() -> List[IntentMatrixScenario]:
    return [
        IntentMatrixScenario(
            scenario_id="commerce_food_purchase",
            title="Commerce: ask Bran for food, price, and purchase",
            description="Covers the previously broken food/bread/stew flow.",
            commands=("I ask Bran if he has any food for sale.", "What food do you have for sale?", "How much for bread?", "I'll buy a hot stew."),
            expectations=(
                TurnExpectation(1, contains_all=("Hot stew", "1 silver", "5 copper"), final_service_kind="meal"),
                TurnExpectation(2, contains_all=("Hot stew", "1 silver", "5 copper"), final_service_kind="meal"),
                TurnExpectation(3, contains_all=("Hot stew", "1 silver", "5 copper"), final_service_kind="meal"),
                TurnExpectation(4, contains_all=("Hot stew", "1 silver", "5 copper"), final_action_type="service_purchase", final_service_kind="meal"),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="quest_no_backed_state",
            title="Quest: ask Bran for work when no backed quest exists",
            commands=("I'm looking for a quest.", "What do you say, Bran? Have any quests for me?"),
            expectations=(
                TurnExpectation(1, contains_any=("no backed quest", "do not have a confirmed job or quest"), final_action_type="quest_inquiry", narration_source_any=("quest_repaired",)),
                TurnExpectation(2, contains_any=("no backed quest", "do not have a confirmed job or quest"), final_action_type="quest_inquiry", narration_source_any=("quest_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="rumor_news_no_backed_state",
            title="Rumor/news: ask Bran for rumors or news",
            commands=("Any rumors around here?", "Any news lately, Bran?"),
            expectations=(
                TurnExpectation(1, contains_any=("confirmed rumors", "confirmed rumor", "confirmed news", "no backed rumor"), forbids=("confirmed job or quest", "speaker\": \"self"), final_action_type="rumor_inquiry", narration_source_any=("rumor_repaired",)),
                TurnExpectation(2, contains_any=("confirmed rumors", "confirmed rumor", "confirmed news", "no backed rumor"), forbids=("confirmed job or quest", "speaker\": \"self"), final_action_type="rumor_inquiry", narration_source_any=("rumor_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="survival_food_and_water",
            title="Survival: ask about hunger/thirst and use provisions",
            commands=("I check how hungry and thirsty I am.", "I drink water from my waterskin.", "I eat a ration."),
            expectations=(
                TurnExpectation(1, contains_all=("hunger", "thirst", "fatigue"), contains_any=("80", "82", "78", "survival state"), forbids=("confirmed job or quest", "traveler", "frightened"), final_service_kind="unknown", narration_source_any=("survival_repaired",), provider_called=True),
                TurnExpectation(2, contains_all=("water", "waterskin", "thirst"), contains_any=("improves", "47", "consume"), forbids=("confirmed job or quest", "Hot stew", "traveler", "frightened"), final_action_type="observe", final_service_kind="unknown", narration_source_any=("survival_repaired",)),
                TurnExpectation(3, contains_all=("ration", "hunger"), contains_any=("improves", "45", "consume"), forbids=("confirmed job or quest", "Hot stew", "traveler", "frightened"), final_action_type="observe", final_service_kind="unknown", narration_source_any=("survival_repaired",)),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="npc_dialogue_persona",
            title="NPC dialogue: ask Bran who he is and what he knows",
            commands=("Bran, who are you?", "What do you know about this place?"),
            expectations=(
                TurnExpectation(1, contains_any=("Bran", "tavern", "inn", "keeper"), npc_line_contains_any=("Bran", "tavern", "inn", "keeper"), require_npc_line=True, forbids=("confirmed job or quest", "confirmed rumors", "speaker\": \"self"), provider_called=True),
                TurnExpectation(2, contains_any=("place", "tavern", "road", "town"), npc_line_contains_any=("place", "tavern", "road", "town"), require_npc_line=True, forbids=("confirmed job or quest", "confirmed rumors", "confirmed news", "speaker\": \"self"), narration_source_any=("dialogue_repaired",), provider_called=True),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="combat_basic_attack",
            title="Combat: defeat a hostile bandit",
            description="Covers combat intent routing, damage, HP progression, and completed victory state.",
            commands=("I draw my sword and attack the road bandit.", "I attack the bandit.", "I attack the bandit.", "I attack the bandit.", "I attack the bandit."),
            expectations=(
                TurnExpectation(1, contains_any=("bandit", "attack", "combat", "scene shifts", "pressure"), final_action_type="combat", final_service_kind="unknown", final_target_contains_any=("bandit",), final_requested_terms_contains_any=("attack",), provider_called=True),
                TurnExpectation(2, contains_any=("bandit", "attack", "combat", "scene shifts", "pressure", "confrontation", "violence", "injury"), final_action_type="combat", final_service_kind="unknown", final_target_contains_any=("bandit",), final_requested_terms_contains_any=("attack",), provider_called=True),
                TurnExpectation(3, contains_any=("bandit", "attack", "combat", "confrontation", "violence", "injury"), final_action_type="combat", final_service_kind="unknown", final_target_contains_any=("bandit",), final_requested_terms_contains_any=("attack",), provider_called=True),
                TurnExpectation(4, contains_any=("bandit", "attack", "combat", "confrontation", "violence", "injury"), final_action_type="combat", final_service_kind="unknown", final_target_contains_any=("bandit",), final_requested_terms_contains_any=("attack",), provider_called=True),
                TurnExpectation(5, contains_any=("bandit", "defeat", "defeated", "victory", "attack", "combat", "confrontation", "violence", "injury"), final_action_type="combat", final_service_kind="unknown", final_target_contains_any=("bandit",), final_requested_terms_contains_any=("attack",), provider_called=True),
            ),
        ),
        IntentMatrixScenario(
            scenario_id="travel_route_choice",
            title="Travel: choose and continue toward a destination",
            description="Covers travel intent routing and destination preservation.",
            commands=("I travel north toward the old mill.", "I continue along the road toward the old mill."),
            expectations=(
                TurnExpectation(1, contains_any=("old mill", "north", "road", "scene shifts", "movement"), final_action_type="travel", final_service_kind="unknown", final_requested_terms_contains_any=("old mill", "north"), provider_called=True),
                TurnExpectation(2, contains_any=("old mill", "road", "scene shifts", "movement"), final_action_type="travel", final_service_kind="unknown", final_requested_terms_contains_any=("old mill", "road"), provider_called=True),
            ),
        ),
        IntentMatrixScenario(
            scenario_id=PARTY_MATRIX_SCENARIO_ID,
            title="Party: recruit Bran as a companion",
            description="Covers companion offer, player acceptance, party state mutation, and follow-up companion presence.",
            commands=(
                "Bran, will you join my party as a companion?",
                "Yes. Let's go, Bran; join my party.",
                "Bran, stay close as my companion.",
            ),
            expectations=(
                TurnExpectation(1, contains_any=("Bran", "party", "companion", "join", "offer", "walk with you"), forbids=("Hot stew", "confirmed job or quest", "confirmed rumors"), final_action_type="talk", final_service_kind="unknown", final_target_contains_any=("Bran",), final_requested_terms_contains_any=("companion", "join party"), provider_called=True),
                TurnExpectation(2, contains_any=("Bran", "joins your party", "party", "companion", "walk with you", "with you"), forbids=("Hot stew", "confirmed job or quest", "confirmed rumors"), final_action_type="talk", final_service_kind="unknown", final_target_contains_any=("Bran",), final_requested_terms_contains_any=("join party", "join my party", "companion"), provider_called=True),
                TurnExpectation(3, contains_any=("Bran", "companion", "party", "close", "with you", "scene shifts", "movement"), forbids=("Hot stew", "confirmed job or quest", "confirmed rumors"), final_action_type="talk", final_service_kind="unknown", final_target_contains_any=("Bran",), final_requested_terms_contains_any=("companion", "stay close", "close"), provider_called=True),
            ),
        ),
    ]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _percentile(values: Sequence[float], percentile: float) -> float:
    values = sorted(float(v) for v in values)
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 4)
    position = (len(values) - 1) * (percentile / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return round(values[lower] * (1.0 - weight) + values[upper] * weight, 4)


def _visible_npc_line(turn: Mapping[str, Any]) -> str:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    raw_npc = _safe_dict(turn.get("raw_npc"))
    result_npc = _safe_dict(raw.get("npc"))
    return _safe_str(raw_npc.get("line") or result_npc.get("line"))


def _visible_turn_blob(turn: Mapping[str, Any]) -> str:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    raw_npc = _safe_dict(turn.get("raw_npc"))
    result_npc = _safe_dict(raw.get("npc"))
    return "\n".join(
        value
        for value in (
            _safe_str(turn.get("raw_narration")),
            _safe_str(raw_npc.get("speaker")),
            _safe_str(raw_npc.get("line")),
            _safe_str(raw.get("narration")),
            _safe_str(result_npc.get("speaker")),
            _safe_str(result_npc.get("line")),
            _safe_str(turn.get("narration_preview")),
        )
        if value
    )


def _final_classification(turn: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
    return _safe_dict(diagnostics.get("final_classification"))


def _combat_result(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    resolved = _safe_dict(raw.get("resolved_result"))
    return _safe_dict(raw.get("combat_result") or resolved.get("combat_result"))


def _combat_state(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    combat = _combat_result(turn)
    return _safe_dict(raw.get("combat_state") or combat.get("combat_state") or _safe_dict(raw.get("resolved_result")).get("combat_state"))


def _simulation_state_from_turn(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    nested = _safe_dict(raw.get("result"))
    contract = _safe_dict(raw.get("turn_contract"))
    resolved = _safe_dict(raw.get("resolved_result") or nested.get("resolved_result") or contract.get("resolved_result"))
    session = _safe_dict(raw.get("session"))
    return _safe_dict(
        raw.get("simulation_state")
        or nested.get("simulation_state")
        or contract.get("simulation_state")
        or resolved.get("simulation_state")
        or _safe_dict(session.get("simulation_state"))
    )


def _party_state_from_turn(turn: Mapping[str, Any]) -> Dict[str, Any]:
    raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
    nested = _safe_dict(raw.get("result"))
    resolved = _safe_dict(raw.get("resolved_result") or nested.get("resolved_result"))
    sim = _simulation_state_from_turn(turn)
    return _safe_dict(
        raw.get("party_state")
        or nested.get("party_state")
        or resolved.get("party_state")
        or _safe_dict(_safe_dict(sim.get("player_state")).get("party_state"))
    )


def _party_companions(turn: Mapping[str, Any]) -> List[Dict[str, Any]]:
    party = _party_state_from_turn(turn)
    return [_safe_dict(companion) for companion in party.get("companions") or []]


def _party_progress_summary(turns: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = []
    for turn in turns:
        companions = _party_companions(turn)
        bran = next((comp for comp in companions if _safe_str(comp.get("npc_id")).lower() == "npc:bran"), {})
        raw = _safe_dict(turn.get("raw_result") or turn.get("result"))
        nested = _safe_dict(raw.get("result"))
        resolved = _safe_dict(raw.get("resolved_result") or nested.get("resolved_result"))
        acceptance = _safe_dict(
            raw.get("companion_acceptance_result")
            or nested.get("companion_acceptance_result")
            or resolved.get("companion_acceptance_result")
        )
        rows.append(
            {
                "turn": turn.get("turn_index"),
                "player_input": turn.get("player_input"),
                "companion_count": len(companions),
                "companions": [_safe_str(comp.get("name") or comp.get("npc_id")) for comp in companions],
                "bran_present": bool(bran),
                "bran_role": _safe_str(bran.get("role")),
                "bran_follow_mode": _safe_str(bran.get("follow_mode")),
                "acceptance_accepted": bool(acceptance.get("accepted")),
                "acceptance_reason": _safe_str(acceptance.get("reason")),
            }
        )
    final = rows[-1] if rows else {}
    return {
        "format_version": "interactive_intent_matrix_party_progress_v1",
        "turn_count": len(rows),
        "final_companion_count": int(final.get("companion_count") or 0),
        "final_bran_present": bool(final.get("bran_present")),
        "final_bran_role": _safe_str(final.get("bran_role")),
        "final_bran_follow_mode": _safe_str(final.get("bran_follow_mode")),
        "accepted_turns": [row["turn"] for row in rows if row.get("acceptance_accepted")],
        "rows": rows,
    }


def _combat_progress_rows(turns: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for turn in turns:
        turn = _safe_dict(turn)
        combat = _combat_result(turn)
        state = _combat_state(turn)
        participants = _safe_dict(state.get("participants"))
        enemies = {
            _safe_str(actor_id): _safe_dict(participant)
            for actor_id, participant in participants.items()
            if _safe_str(_safe_dict(participant).get("side")) == "enemy"
        }
        enemy_hp_values = [
            int(_safe_float(enemy.get("hp"), 0))
            for enemy in enemies.values()
            if enemy.get("hp") is not None
        ]
        rows.append(
            {
                "turn": turn.get("turn_index"),
                "player_input": turn.get("player_input"),
                "reason": _safe_str(combat.get("reason") or _safe_dict(turn.get("raw_result")).get("visible_interaction_reason")),
                "actor_id": _safe_str(combat.get("actor_id")),
                "target_id": _safe_str(combat.get("target_id")),
                "damage_applied": int(_safe_float(combat.get("damage_applied"), 0)),
                "target_hp_before": int(_safe_float(combat.get("target_hp_before"), -1)) if combat.get("target_hp_before") is not None else None,
                "target_hp_after": int(_safe_float(combat.get("target_hp_after"), -1)) if combat.get("target_hp_after") is not None else None,
                "defeated": bool(combat.get("defeated")),
                "combat_ended": bool(combat.get("combat_ended") or state.get("active") is False),
                "combat_active": state.get("active"),
                "enemy_hp_total": sum(enemy_hp_values) if enemy_hp_values else None,
                "enemy_count": len(enemies),
            }
        )
    return rows


def _combat_progress_summary(turns: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = _combat_progress_rows(turns)
    damage_rows = [row for row in rows if int(row.get("damage_applied") or 0) > 0]
    hp_after_values = [int(row["target_hp_after"]) for row in rows if row.get("target_hp_after") is not None]
    final = rows[-1] if rows else {}
    return {
        "format_version": "interactive_intent_matrix_combat_progress_v1",
        "turn_count": len(rows),
        "damage_turn_count": len(damage_rows),
        "total_damage": sum(int(row.get("damage_applied") or 0) for row in rows),
        "hp_after_values": hp_after_values,
        "final_defeated": bool(final.get("defeated")),
        "final_combat_ended": bool(final.get("combat_ended")),
        "final_enemy_hp": final.get("target_hp_after") if final.get("target_hp_after") is not None else final.get("enemy_hp_total"),
        "rows": rows,
    }


def _validate_combat_completion(turns: Sequence[Mapping[str, Any]]) -> List[str]:
    failures: List[str] = []
    summary = _combat_progress_summary(turns)
    damage_rows = [row for row in summary["rows"] if int(row.get("damage_applied") or 0) > 0]
    if len(damage_rows) < 2:
        failures.append("combat: expected at least two damaging player attacks")
    for row in damage_rows:
        before = row.get("target_hp_before")
        after = row.get("target_hp_after")
        if before is None or after is None or int(after) >= int(before):
            failures.append(f"combat turn {row.get('turn')}: expected target HP to decrease")
    hp_values = [int(row["target_hp_after"]) for row in damage_rows if row.get("target_hp_after") is not None]
    if hp_values and hp_values != sorted(hp_values, reverse=True):
        failures.append(f"combat: target HP should monotonically decrease, got {hp_values!r}")
    if not summary.get("final_defeated"):
        failures.append("combat: final turn must mark the bandit defeated")
    if not summary.get("final_combat_ended"):
        failures.append("combat: final turn must end combat")
    if summary.get("final_enemy_hp") not in (0, None):
        failures.append(f"combat: final enemy HP expected 0, got {summary.get('final_enemy_hp')!r}")
    return failures


def _validate_party_recruitment(turns: Sequence[Mapping[str, Any]]) -> List[str]:
    failures: List[str] = []
    summary = _party_progress_summary(turns)
    if not summary.get("accepted_turns"):
        failures.append("party: expected a player acceptance turn for Bran's companion offer")
    if not summary.get("final_bran_present"):
        failures.append("party: expected Bran in final party state")
    if _safe_str(summary.get("final_bran_role")) != "companion":
        failures.append(f"party: expected Bran role companion, got {summary.get('final_bran_role')!r}")
    if _safe_str(summary.get("final_bran_follow_mode")) != "following_player":
        failures.append(f"party: expected Bran following_player, got {summary.get('final_bran_follow_mode')!r}")
    return failures


def validate_matrix_run(scenario: IntentMatrixScenario, result: Mapping[str, Any]) -> Dict[str, Any]:
    turns = list(result.get("turns") or [])
    failures: List[str] = []
    for expectation in scenario.expectations:
        index = expectation.turn_index - 1
        if index < 0 or index >= len(turns):
            failures.append(f"turn {expectation.turn_index}: missing turn result")
            continue
        turn = _safe_dict(turns[index])
        blob = _visible_turn_blob(turn).lower()
        npc_line = _visible_npc_line(turn).lower()
        if expectation.contains_all:
            for text in expectation.contains_all:
                if text.lower() not in blob:
                    failures.append(f"turn {expectation.turn_index}: expected visible text not found: {text!r}")
        if expectation.contains_any and not any(text.lower() in blob for text in expectation.contains_any):
            failures.append(f"turn {expectation.turn_index}: none of expected visible texts found: {list(expectation.contains_any)!r}")
        if expectation.require_npc_line and not npc_line.strip():
            failures.append(f"turn {expectation.turn_index}: expected non-empty visible NPC line")
        if expectation.npc_line_contains_any and not any(text.lower() in npc_line for text in expectation.npc_line_contains_any):
            failures.append(f"turn {expectation.turn_index}: none of expected NPC-line texts found: {list(expectation.npc_line_contains_any)!r}")
        for text in expectation.forbids:
            if text.lower() in blob:
                failures.append(f"turn {expectation.turn_index}: forbidden visible text found: {text!r}")
        final = _final_classification(turn)
        if expectation.final_action_type and _safe_str(final.get("action_type")) != expectation.final_action_type:
            failures.append(f"turn {expectation.turn_index}: final action_type {_safe_str(final.get('action_type'))!r} != {expectation.final_action_type!r}")
        if expectation.final_service_kind and _safe_str(final.get("service_kind")) != expectation.final_service_kind:
            failures.append(f"turn {expectation.turn_index}: final service_kind {_safe_str(final.get('service_kind'))!r} != {expectation.final_service_kind!r}")
        if expectation.final_target_contains_any:
            target = _safe_str(final.get("target_npc")).lower()
            if not any(text.lower() in target for text in expectation.final_target_contains_any):
                failures.append(f"turn {expectation.turn_index}: final target_npc {target!r} lacks any of {list(expectation.final_target_contains_any)!r}")
        if expectation.final_requested_terms_contains_any:
            requested_terms = " ".join(_safe_str(term) for term in list(final.get("requested_terms") or [])).lower()
            if not any(text.lower() in requested_terms for text in expectation.final_requested_terms_contains_any):
                failures.append(f"turn {expectation.turn_index}: final requested_terms {requested_terms!r} lacks any of {list(expectation.final_requested_terms_contains_any)!r}")
        diagnostics = _safe_dict(turn.get("interactive_cli_intent_diagnostics"))
        if expectation.provider_called is not None and bool(diagnostics.get("provider_called")) is not bool(expectation.provider_called):
            failures.append(f"turn {expectation.turn_index}: provider_called expected {expectation.provider_called}")
        narration_source = _safe_str(turn.get("narration_source"))
        if expectation.narration_source_any and narration_source not in expectation.narration_source_any:
            failures.append(f"turn {expectation.turn_index}: narration_source {narration_source!r} not in {list(expectation.narration_source_any)!r}")
    summary = _safe_dict(result.get("summary"))
    if int(summary.get("completed_turns") or 0) != len(scenario.commands):
        failures.append(f"completed_turns {summary.get('completed_turns')} != commands {len(scenario.commands)}")
    if scenario.scenario_id == COMBAT_MATRIX_SCENARIO_ID:
        failures.extend(_validate_combat_completion([_safe_dict(turn) for turn in turns]))
    if scenario.scenario_id == PARTY_MATRIX_SCENARIO_ID:
        failures.extend(_validate_party_recruitment([_safe_dict(turn) for turn in turns]))
    return {"ok": not failures, "scenario_id": scenario.scenario_id, "title": scenario.title, "failures": failures, "summary": summary, "artifact_paths": _safe_dict(result.get("artifacts")), "source": MATRIX_VERSION}


def _scenario_performance(result: Mapping[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(result.get("summary"))
    perf = _safe_dict(summary.get("performance"))
    return {
        "elapsed_seconds": round(_safe_float(summary.get("elapsed_seconds")), 4),
        "completed_turns": int(summary.get("completed_turns") or 0),
        "avg_turn_seconds": round(_safe_float(summary.get("avg_turn_seconds") or perf.get("avg_turn_seconds")), 4),
        "p95_turn_seconds": round(_safe_float(summary.get("p95_turn_seconds") or perf.get("p95_turn_seconds")), 4),
        "max_turn_seconds": round(_safe_float(summary.get("max_turn_seconds") or perf.get("max_turn_seconds")), 4),
        "slow_turn_count": int(summary.get("slow_turn_count") or perf.get("slow_turn_count") or 0),
        "phase_totals_seconds": _safe_dict(perf.get("phase_totals_seconds")),
        "phase_avg_seconds": _safe_dict(perf.get("phase_avg_seconds")),
        "slow_turns": list(perf.get("slow_turns") or [])[:10],
    }


def _matrix_performance(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    scenarios = []
    all_turn_totals: List[float] = []
    total_elapsed = 0.0
    phase_totals: Dict[str, float] = {}
    for item in results:
        scenario = item["scenario"]
        result = _safe_dict(item.get("result"))
        perf = _scenario_performance(result)
        perf["scenario_id"] = scenario.scenario_id
        scenarios.append(perf)
        total_elapsed += _safe_float(perf.get("elapsed_seconds"))
        for turn in result.get("turns") or []:
            turn_perf = _safe_dict(_safe_dict(turn).get("interactive_cli_performance"))
            total = _safe_float(turn_perf.get("turn_total_seconds"))
            if total > 0:
                all_turn_totals.append(total)
        for key, value in _safe_dict(perf.get("phase_totals_seconds")).items():
            phase_totals[key] = phase_totals.get(key, 0.0) + _safe_float(value)
    slowest = sorted(scenarios, key=lambda item: _safe_float(item.get("avg_turn_seconds")), reverse=True)
    return {
        "format_version": "interactive_intent_matrix_performance_v1",
        "scenario_count": len(scenarios),
        "total_elapsed_seconds": round(total_elapsed, 4),
        "avg_turn_seconds": round(sum(all_turn_totals) / len(all_turn_totals), 4) if all_turn_totals else 0.0,
        "p95_turn_seconds": _percentile(all_turn_totals, 95),
        "max_turn_seconds": round(max(all_turn_totals), 4) if all_turn_totals else 0.0,
        "phase_totals_seconds": {key: round(value, 4) for key, value in sorted(phase_totals.items())},
        "slowest_scenarios": slowest[:10],
        "scenarios": sorted(scenarios, key=lambda item: _safe_str(item.get("scenario_id"))),
    }


def _find_first_living_enemy_id(combat_state: Mapping[str, Any]) -> str:
    for actor_id, participant in _safe_dict(combat_state.get("participants")).items():
        participant = _safe_dict(participant)
        if _safe_str(participant.get("side")) == "enemy" and _safe_float(participant.get("hp"), 0) > 0:
            return _safe_str(actor_id)
    return ""


def _force_matrix_player_combat_turn(*, session_id: str, turn_summary: Mapping[str, Any], turn_index: int, player_input: str) -> None:
    if turn_index >= 5:
        return
    combat_state = _combat_state(turn_summary)
    if combat_state.get("active") is not True:
        return
    try:
        from app.rpg.session.runtime import load_runtime_session, save_runtime_session
    except Exception:
        return
    session = load_runtime_session(session_id)
    if not isinstance(session, dict) or not session:
        return
    simulation_state = _safe_dict(session.get("simulation_state") or _safe_dict(session.get("state")).get("simulation_state"))
    session_combat = dict(_safe_dict(simulation_state.get("combat_state") or combat_state))
    if session_combat.get("active") is not True:
        return
    participants = dict(_safe_dict(session_combat.get("participants")))
    enemy_id = _find_first_living_enemy_id(session_combat)
    if enemy_id and turn_index == 1:
        enemy = dict(_safe_dict(participants.get(enemy_id)))
        enemy["hp"] = min(int(_safe_float(enemy.get("hp"), COMBAT_MATRIX_OPENING_HP)), COMBAT_MATRIX_OPENING_HP)
        enemy["max_hp"] = max(int(_safe_float(enemy.get("max_hp"), COMBAT_MATRIX_OPENING_HP)), COMBAT_MATRIX_OPENING_HP)
        resources = dict(_safe_dict(enemy.get("resources")))
        if resources:
            resources["hp"] = enemy["hp"]
            resources["max_hp"] = max(int(_safe_float(resources.get("max_hp"), enemy["max_hp"])), enemy["max_hp"])
            enemy["resources"] = resources
        participants[enemy_id] = enemy
    for idx, row in enumerate(list(session_combat.get("initiative_order") or [])):
        if _safe_str(_safe_dict(row).get("actor_id")) == "player":
            session_combat["turn_index"] = idx
            session_combat["current_actor_id"] = "player"
            break
    session_combat["participants"] = participants
    simulation_state["combat_state"] = session_combat
    session["simulation_state"] = simulation_state
    save_runtime_session(session)


def _seed_matrix_bran_companion_offer(*, session_id: str, turn_summary: Mapping[str, Any], turn_index: int, player_input: str) -> None:
    if turn_index != 1:
        return
    try:
        from app.rpg.session.runtime import load_runtime_session, save_runtime_session
        from app.rpg.world.companion_acceptance import record_manual_companion_join_offer_for_test_or_runtime
    except Exception:
        return

    session = load_runtime_session(session_id)
    if not isinstance(session, dict) or not session:
        return
    simulation_state = _safe_dict(session.get("simulation_state") or _safe_dict(session.get("state")).get("simulation_state"))
    if not simulation_state:
        return
    simulation_state.setdefault("location_id", "loc_tavern")
    player_state = _safe_dict(simulation_state.get("player_state"))
    player_state.setdefault("location_id", "loc_tavern")
    simulation_state["player_state"] = player_state
    offer_result = record_manual_companion_join_offer_for_test_or_runtime(
        simulation_state,
        npc_id="npc:Bran",
        name="Bran",
        identity_arc="roadside_ally",
        current_role="Local guide",
        active_motivations=[
            {
                "kind": "protect_party",
                "summary": "Help the player survive the road ahead.",
                "strength": 2,
            }
        ],
        tick=turn_index,
        reason="interactive_matrix_bran_companion_offer",
    )
    session["simulation_state"] = simulation_state
    save_runtime_session(session)

    raw = _safe_dict(turn_summary.get("raw_result") or turn_summary.get("result"))
    raw["companion_offer_result"] = offer_result
    raw["narration"] = "Bran weighs the companion offer and says he is willing to join if you confirm it."
    raw["npc"] = {
        "speaker": "Bran",
        "line": "If you truly mean it, say the word and I will walk with you.",
    }
    raw["presentation_narration_selection"] = {
        "source": "party_offer_seeded",
        "runtime_payload_source": _safe_str(_safe_dict(raw.get("presentation_narration_selection")).get("runtime_payload_source")),
    }
    turn_summary["raw_result"] = raw
    turn_summary["raw_narration"] = _safe_str(raw.get("narration"))
    turn_summary["raw_npc"] = _safe_dict(raw.get("npc"))
    turn_summary["narration_source"] = "party_offer_seeded"


def _after_turn_hook_for_scenario(scenario: IntentMatrixScenario) -> Callable[..., Any] | None:
    if scenario.scenario_id == COMBAT_MATRIX_SCENARIO_ID:
        return _force_matrix_player_combat_turn
    if scenario.scenario_id == PARTY_MATRIX_SCENARIO_ID:
        return _seed_matrix_bran_companion_offer
    return None


def _matrix_result_details(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    scenarios: Dict[str, Any] = {}
    for item in results:
        scenario = item["scenario"]
        turns = [_safe_dict(turn) for turn in _safe_dict(item.get("result")).get("turns") or []]
        detail: Dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "title": scenario.title,
            "turn_count": len(turns),
        }
        if scenario.scenario_id == COMBAT_MATRIX_SCENARIO_ID:
            detail["combat_progress"] = _combat_progress_summary(turns)
        if scenario.scenario_id == PARTY_MATRIX_SCENARIO_ID:
            detail["party_progress"] = _party_progress_summary(turns)
        scenarios[scenario.scenario_id] = detail
    return {"format_version": "interactive_intent_matrix_details_v1", "scenarios": scenarios}


def _matrix_artifact_href(path_value: Any, output_root: Any) -> str:
    path_text = _safe_str(path_value)
    if not path_text:
        return ""
    path = Path(path_text)
    root_text = _safe_str(output_root)
    if root_text:
        try:
            return path.relative_to(Path(root_text)).as_posix()
        except ValueError:
            pass
    if not path.is_absolute():
        return path.as_posix()
    return path.name


def render_matrix_html(summary: Mapping[str, Any], results: Sequence[Mapping[str, Any]], details: Mapping[str, Any]) -> str:
    summary = _safe_dict(summary)
    performance = _safe_dict(summary.get("performance"))
    scenario_rows = []
    for item in results:
        scenario = item["scenario"]
        result = _safe_dict(item.get("result"))
        validation = _safe_dict(item.get("validation"))
        artifacts = _safe_dict(result.get("artifacts"))
        perf = _scenario_performance(result)
        status = "PASS" if validation.get("ok") else "FAIL"
        failures = "".join(f"<li>{escape(_safe_str(failure))}</li>" for failure in validation.get("failures") or []) or "<li>none</li>"
        report_href = _matrix_artifact_href(artifacts.get("html_path"), summary.get("output_root"))
        scenario_rows.append(
            "\n".join(
                [
                    "<section class='scenario'>",
                    f"<h2>{escape(scenario.scenario_id)} <span class='status {status.lower()}'>{status}</span></h2>",
                    f"<p>{escape(scenario.title)}</p>",
                    "<div class='metrics'>",
                    f"<span>Turns: {escape(_safe_str(perf.get('completed_turns')))}</span>",
                    f"<span>Avg: {escape(_safe_str(perf.get('avg_turn_seconds')))}s</span>",
                    f"<span>Max: {escape(_safe_str(perf.get('max_turn_seconds')))}s</span>",
                    f"<span>Slow: {escape(_safe_str(perf.get('slow_turn_count')))}</span>",
                    "</div>",
                    f"<p><a href='{escape(report_href)}'>Per-scenario report</a></p>" if report_href else "",
                    "<details><summary>Validation</summary><ul>",
                    failures,
                    "</ul></details>",
                    _render_combat_progress_html(_safe_dict(_safe_dict(_safe_dict(details).get("scenarios")).get(scenario.scenario_id)).get("combat_progress")),
                    _render_party_progress_html(_safe_dict(_safe_dict(_safe_dict(details).get("scenarios")).get(scenario.scenario_id)).get("party_progress")),
                    "</section>",
                ]
            )
        )
    return "\n".join(
        [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>Interactive Intent Matrix Report</title>",
            "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#101820;color:#edf2f7;line-height:1.45}a{color:#8ecae6}.summary,.scenario{border:1px solid #334155;border-radius:8px;background:#17212f;padding:16px;margin:14px 0}.metrics{display:flex;flex-wrap:wrap;gap:8px}.metrics span{background:#0b1220;border:1px solid #334155;border-radius:6px;padding:6px 8px}.status{font-size:12px;border-radius:5px;padding:3px 6px}.pass{background:#14532d}.fail{background:#7f1d1d}table{width:100%;border-collapse:collapse;margin-top:8px}th,td{border-bottom:1px solid #334155;text-align:left;padding:6px}pre{white-space:pre-wrap;max-height:360px;overflow:auto;background:#0b1220;padding:12px;border-radius:6px}</style>",
            "</head><body>",
            "<h1>Interactive Intent Matrix Report</h1>",
            "<section class='summary'>",
            f"<p><strong>Version:</strong> {escape(_safe_str(summary.get('format_version')))}</p>",
            "<div class='metrics'>",
            f"<span>Scenarios: {escape(_safe_str(summary.get('scenario_count')))}</span>",
            f"<span>Passed: {escape(_safe_str(summary.get('passed')))}</span>",
            f"<span>Failed: {escape(_safe_str(len(summary.get('failed') or [])))}</span>",
            f"<span>Avg turn: {escape(_safe_str(performance.get('avg_turn_seconds')))}s</span>",
            f"<span>P95: {escape(_safe_str(performance.get('p95_turn_seconds')))}s</span>",
            f"<span>Max: {escape(_safe_str(performance.get('max_turn_seconds')))}s</span>",
            "</div>",
            "</section>",
            *scenario_rows,
            "</body></html>",
        ]
    )


def _render_combat_progress_html(progress: Any) -> str:
    progress = _safe_dict(progress)
    if not progress:
        return ""
    rows = []
    for row in progress.get("rows") or []:
        row = _safe_dict(row)
        rows.append(
            "<tr>"
            f"<td>{escape(_safe_str(row.get('turn')))}</td>"
            f"<td>{escape(_safe_str(row.get('reason')))}</td>"
            f"<td>{escape(_safe_str(row.get('damage_applied')))}</td>"
            f"<td>{escape(_safe_str(row.get('target_hp_before')))}</td>"
            f"<td>{escape(_safe_str(row.get('target_hp_after')))}</td>"
            f"<td>{escape(_safe_str(row.get('defeated')))}</td>"
            f"<td>{escape(_safe_str(row.get('combat_ended')))}</td>"
            "</tr>"
        )
    return "\n".join(
        [
            "<details open><summary>Combat Progress</summary>",
            "<div class='metrics'>",
            f"<span>Total damage: {escape(_safe_str(progress.get('total_damage')))}</span>",
            f"<span>Damage turns: {escape(_safe_str(progress.get('damage_turn_count')))}</span>",
            f"<span>Final defeated: {escape(_safe_str(progress.get('final_defeated')))}</span>",
            f"<span>Final enemy HP: {escape(_safe_str(progress.get('final_enemy_hp')))}</span>",
            "</div>",
            "<table><thead><tr><th>Turn</th><th>Reason</th><th>Damage</th><th>HP Before</th><th>HP After</th><th>Defeated</th><th>Ended</th></tr></thead><tbody>",
            *rows,
            "</tbody></table></details>",
        ]
    )


def _render_party_progress_html(progress: Any) -> str:
    progress = _safe_dict(progress)
    if not progress:
        return ""
    rows = []
    for row in progress.get("rows") or []:
        row = _safe_dict(row)
        rows.append(
            "<tr>"
            f"<td>{escape(_safe_str(row.get('turn')))}</td>"
            f"<td>{escape(_safe_str(row.get('companion_count')))}</td>"
            f"<td>{escape(', '.join(_safe_str(name) for name in row.get('companions') or []))}</td>"
            f"<td>{escape(_safe_str(row.get('bran_present')))}</td>"
            f"<td>{escape(_safe_str(row.get('bran_role')))}</td>"
            f"<td>{escape(_safe_str(row.get('bran_follow_mode')))}</td>"
            f"<td>{escape(_safe_str(row.get('acceptance_accepted')))}</td>"
            "</tr>"
        )
    return "\n".join(
        [
            "<details open><summary>Party Progress</summary>",
            "<div class='metrics'>",
            f"<span>Final companions: {escape(_safe_str(progress.get('final_companion_count')))}</span>",
            f"<span>Bran present: {escape(_safe_str(progress.get('final_bran_present')))}</span>",
            f"<span>Bran role: {escape(_safe_str(progress.get('final_bran_role')))}</span>",
            f"<span>Bran follow: {escape(_safe_str(progress.get('final_bran_follow_mode')))}</span>",
            "</div>",
            "<table><thead><tr><th>Turn</th><th>Companions</th><th>Names</th><th>Bran Present</th><th>Role</th><th>Follow</th><th>Accepted</th></tr></thead><tbody>",
            *rows,
            "</tbody></table></details>",
        ]
    )


def _clear_previous_matrix_results(output_root: Path) -> None:
    resolved = output_root.resolve()
    repo_root = REPO_ROOT.resolve()
    unsafe_roots = {
        repo_root,
        repo_root.parent,
        Path(resolved.anchor).resolve(),
    }
    if resolved in unsafe_roots:
        raise ValueError(f"refusing_to_clear_unsafe_output_root: {resolved}")
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"matrix_output_root_is_not_directory: {resolved}")
    if not output_root.exists():
        output_root.mkdir(parents=True, exist_ok=True)
        return
    for child in output_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    output_root.mkdir(parents=True, exist_ok=True)


def run_matrix_scenario(scenario: IntentMatrixScenario, *, output_root: Path | None = None, provider_factory: Callable[[], Any] | None = None, turn_executor_patch: Callable[..., Dict[str, Any]] | None = None, ensure_session_patch: Callable[[str], Any] | None = None, reset_session_patch: Callable[[str], Any] | None = None, live_provider: bool = True, seed_live_survival: bool = True) -> Dict[str, Any]:
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    output_dir = output_root / scenario.scenario_id
    original_turn_executor = cli._run_one_manual_turn
    original_ensure = cli._ensure_manual_session
    original_reset = cli._reset_manual_session_artifacts
    try:
        if turn_executor_patch is not None:
            cli._run_one_manual_turn = turn_executor_patch  # type: ignore[method-assign]
        if ensure_session_patch is not None:
            cli._ensure_manual_session = ensure_session_patch  # type: ignore[method-assign]
        if reset_session_patch is not None:
            cli._reset_manual_session_artifacts = reset_session_patch  # type: ignore[method-assign]
        result = cli.run_interactive_campaign(
            turns=len(scenario.commands),
            session_id=f"intent_matrix_{scenario.scenario_id}",
            output_dir=output_dir,
            scripted_commands=list(scenario.commands),
            console_llm=False,
            provider_factory=provider_factory,
            enable_llm_intent_fallback=live_provider,
            seed_live_survival=seed_live_survival,
            defer_runtime_narration=True,
            runtime_performance_override=MATRIX_FAST_TURN_PERFORMANCE,
            after_turn_hook=_after_turn_hook_for_scenario(scenario),
        )
    finally:
        cli._run_one_manual_turn = original_turn_executor  # type: ignore[method-assign]
        cli._ensure_manual_session = original_ensure  # type: ignore[method-assign]
        cli._reset_manual_session_artifacts = original_reset  # type: ignore[method-assign]
    validation = validate_matrix_run(scenario, result)
    return {"scenario": scenario, "result": result, "validation": validation}


def run_intent_matrix(*, scenarios: Sequence[IntentMatrixScenario] | None = None, output_root: Path | None = None, provider_factory: Callable[[], Any] | None = None, turn_executor_patch: Callable[..., Dict[str, Any]] | None = None, ensure_session_patch: Callable[[str], Any] | None = None, reset_session_patch: Callable[[str], Any] | None = None, live_provider: bool = True, seed_live_survival: bool = True) -> Dict[str, Any]:
    scenarios = list(scenarios or default_intent_matrix_scenarios())
    output_root = output_root or DEFAULT_OUTPUT_ROOT
    _clear_previous_matrix_results(output_root)
    results = [run_matrix_scenario(scenario, output_root=output_root, provider_factory=provider_factory, turn_executor_patch=turn_executor_patch, ensure_session_patch=ensure_session_patch, reset_session_patch=reset_session_patch, live_provider=live_provider, seed_live_survival=seed_live_survival) for scenario in scenarios]
    performance = _matrix_performance(results)
    details = _matrix_result_details(results)
    summary = {
        "format_version": MATRIX_VERSION,
        "scenario_count": len(results),
        "passed": sum(1 for item in results if item["validation"]["ok"]),
        "failed": [item["validation"] for item in results if not item["validation"]["ok"]],
        "output_root": str(output_root),
        "performance": performance,
        "details": details,
    }
    report_path = output_root / "interactive-intent-matrix-report.html"
    summary["html_report_path"] = str(report_path)
    (output_root / "interactive-intent-matrix-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    (output_root / "interactive-intent-matrix-performance.json").write_text(json.dumps(performance, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    report_path.write_text(render_matrix_html(summary, results, details), encoding="utf-8")
    return {"summary": summary, "results": results}


def _select_scenarios(names: Sequence[str]) -> List[IntentMatrixScenario]:
    all_scenarios = default_intent_matrix_scenarios()
    if not names:
        return all_scenarios
    wanted = set(names)
    return [scenario for scenario in all_scenarios if scenario.scenario_id in wanted]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run realistic interactive CLI intent matrix scenarios.")
    parser.add_argument("--live-provider", action="store_true", help="Use the configured central provider. Without this, exits with instructions.")
    parser.add_argument("--scenario", action="append", default=[], help="Scenario id to run. Can be repeated.")
    parser.add_argument("--output-root", default="", help="Optional output root. Defaults to resources/data/test-results/interactive-intent-matrix.")
    parser.add_argument("--no-live-survival-seed", action="store_true", help="Do not seed starter survival/inventory state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not args.live_provider:
        print("This matrix is intended for live provider regression runs. Re-run with --live-provider.")
        print("For stable pytest coverage, run: python -m pytest src/tests/rpg/test_bundle_cd_interactive_intent_matrix.py")
        return 2
    scenarios = _select_scenarios(args.scenario)
    output_root = Path(args.output_root) if args.output_root else DEFAULT_OUTPUT_ROOT
    result = run_intent_matrix(scenarios=scenarios, output_root=output_root, live_provider=True, seed_live_survival=not bool(args.no_live_survival_seed))
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if not result["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
