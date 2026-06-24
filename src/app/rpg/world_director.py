"""World director and campaign pacing helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

ArcStatus = Literal["active", "paused", "resolved", "failed"]
LoopKind = Literal["none", "location_loop", "npc_loop", "action_loop"]


@dataclass(frozen=True)
class StoryArc:
    arc_id: str
    title: str
    status: ArcStatus = "active"
    pressure: int = 0
    beats_completed: int = 0
    threat: str = ""

    def advance(self, amount: int = 1) -> "StoryArc":
        return replace(self, beats_completed=self.beats_completed + max(0, amount))

    def with_pressure(self, amount: int) -> "StoryArc":
        return replace(self, pressure=max(0, min(100, self.pressure + amount)))


@dataclass(frozen=True)
class DirectorState:
    arcs: tuple[StoryArc, ...] = ()
    recent_locations: tuple[str, ...] = ()
    recent_npcs: tuple[str, ...] = ()
    recent_actions: tuple[str, ...] = ()
    danger_level: int = 0
    downtime: int = 0

    def active_arcs(self) -> tuple[StoryArc, ...]:
        return tuple(arc for arc in self.arcs if arc.status == "active")


@dataclass(frozen=True)
class LoopReport:
    kind: LoopKind
    repeated_value: str = ""
    count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "repeated_value": self.repeated_value, "count": self.count}


def detect_loop(values: Sequence[str], loop_kind: LoopKind, threshold: int = 3) -> LoopReport:
    if len(values) < threshold:
        return LoopReport("none")
    tail = tuple(values[-threshold:])
    if len(set(tail)) == 1:
        return LoopReport(loop_kind, tail[0], threshold)
    return LoopReport("none")


def detect_director_loops(state: DirectorState) -> tuple[LoopReport, ...]:
    reports = (
        detect_loop(state.recent_locations, "location_loop"),
        detect_loop(state.recent_npcs, "npc_loop"),
        detect_loop(state.recent_actions, "action_loop"),
    )
    return tuple(report for report in reports if report.kind != "none")


def apply_pacing_pressure(state: DirectorState) -> DirectorState:
    loops = detect_director_loops(state)
    pressure_delta = 5 + (5 * len(loops)) + max(0, state.downtime)
    return replace(state, arcs=tuple(arc.with_pressure(pressure_delta) for arc in state.arcs))


def grounded_director_suggestions(state: DirectorState, valid_actions: Sequence[str]) -> tuple[str, ...]:
    suggestions: list[str] = []
    for arc in state.active_arcs():
        if arc.threat:
            suggestions.append(f"Address {arc.title}: {arc.threat}")
        else:
            suggestions.append(f"Advance {arc.title}")
    suggestions.extend(action for action in valid_actions if action not in suggestions)
    return tuple(suggestions[:5])


def advance_arc(state: DirectorState, arc_id: str, amount: int = 1) -> DirectorState:
    return replace(state, arcs=tuple(arc.advance(amount) if arc.arc_id == arc_id else arc for arc in state.arcs))


def director_report_payload(state: DirectorState, valid_actions: Sequence[str]) -> dict[str, object]:
    return {
        "active_arcs": [arc.arc_id for arc in state.active_arcs()],
        "loops": [report.as_dict() for report in detect_director_loops(state)],
        "danger_level": state.danger_level,
        "downtime": state.downtime,
        "suggested_actions": list(grounded_director_suggestions(state, valid_actions)),
    }
