"""Deterministic NPC schedules and offscreen activity helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

DayPart = Literal["morning", "afternoon", "evening", "night"]
EventVisibility = Literal["hidden", "known"]
DiscoveryMethod = Literal["rumor", "investigation", "witness", "scouting", "party_report", "letter", "visible_change"]


@dataclass(frozen=True)
class NpcScheduleEntry:
    npc_id: str
    day_part: DayPart
    location_id: str
    activity: str
    public_hint: str = ""


@dataclass(frozen=True)
class OffscreenEvent:
    event_id: str
    turn: int
    npc_id: str
    location_id: str
    visibility: EventVisibility
    summary: str
    tags: tuple[str, ...] = ()

    def known_copy(self, *, method: DiscoveryMethod, public_summary: str | None = None) -> "OffscreenEvent":
        summary = public_summary if public_summary is not None else self.summary
        return replace(self, visibility="known", summary=summary, tags=self.tags + (f"discovered:{method}",))

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "turn": self.turn,
            "npc_id": self.npc_id,
            "location_id": self.location_id,
            "visibility": self.visibility,
            "summary": self.summary,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class OffscreenActivityState:
    schedule: tuple[NpcScheduleEntry, ...] = ()
    hidden_events: tuple[OffscreenEvent, ...] = ()
    known_events: tuple[OffscreenEvent, ...] = ()

    def entries_for(self, day_part: DayPart) -> tuple[NpcScheduleEntry, ...]:
        entries = [entry for entry in self.schedule if entry.day_part == day_part]
        return tuple(sorted(entries, key=lambda entry: (entry.npc_id, entry.location_id)))

    def with_events(self, events: Sequence[OffscreenEvent]) -> "OffscreenActivityState":
        hidden = list(self.hidden_events)
        known = list(self.known_events)
        for event in events:
            if event.visibility == "hidden":
                hidden.append(event)
            else:
                known.append(event)
        return replace(self, hidden_events=tuple(hidden), known_events=tuple(known))

    def reveal_event(self, event_id: str, *, method: DiscoveryMethod, public_summary: str | None = None) -> "OffscreenActivityState":
        hidden = list(self.hidden_events)
        known = list(self.known_events)
        for index, event in enumerate(hidden):
            if event.event_id == event_id:
                known.append(event.known_copy(method=method, public_summary=public_summary))
                hidden.pop(index)
                break
        return replace(self, hidden_events=tuple(hidden), known_events=tuple(known))


def day_part_for_turn(turn: int) -> DayPart:
    return ("morning", "afternoon", "evening", "night")[(turn // 6) % 4]


def generate_offscreen_events(state: OffscreenActivityState, *, turn: int) -> tuple[OffscreenEvent, ...]:
    day_part = day_part_for_turn(turn)
    events: list[OffscreenEvent] = []
    for entry in state.entries_for(day_part):
        event_id = f"offscreen:{turn}:{entry.npc_id}:{entry.location_id}"
        events.append(
            OffscreenEvent(
                event_id=event_id,
                turn=turn,
                npc_id=entry.npc_id,
                location_id=entry.location_id,
                visibility="hidden",
                summary=f"{entry.npc_id} {entry.activity} at {entry.location_id}.",
                tags=("offscreen", day_part),
            )
        )
    return tuple(events)


def public_hints_for_location(state: OffscreenActivityState, location_id: str) -> tuple[str, ...]:
    hints = [entry.public_hint for entry in state.schedule if entry.location_id == location_id and entry.public_hint]
    return tuple(sorted(set(hints)))


def offscreen_report_payload(state: OffscreenActivityState) -> dict[str, object]:
    return {
        "hidden_count": len(state.hidden_events),
        "known_count": len(state.known_events),
        "known_events": [event.as_dict() for event in state.known_events],
    }


def schedule_by_npc(schedule: Sequence[NpcScheduleEntry]) -> Mapping[str, tuple[NpcScheduleEntry, ...]]:
    grouped: dict[str, list[NpcScheduleEntry]] = {}
    for entry in schedule:
        grouped.setdefault(entry.npc_id, []).append(entry)
    return {npc_id: tuple(entries) for npc_id, entries in sorted(grouped.items())}
