"""Runtime quest lead, deadline, and journal adapters for RPG Phase 22."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.rpg.quest_chronicle import QuestObjective, QuestState, chronicle_payload, rumor_to_quest

QUEST_RUNTIME_SOURCE = "phase22_quest_runtime_v1"
DeadlineStatus = Literal["none", "active", "due_now", "expired"]
LeadStatus = Literal["rumor", "lead", "quest"]


@dataclass(frozen=True)
class QuestLead:
    lead_id: str
    summary: str
    clue: str
    location_id: str = ""
    npc_id: str = ""
    status: LeadStatus = "lead"

    def as_dict(self) -> dict[str, object]:
        return {
            "lead_id": self.lead_id,
            "summary": self.summary,
            "clue": self.clue,
            "location_id": self.location_id,
            "npc_id": self.npc_id,
            "status": self.status,
        }


def build_quest_runtime_report(turn_result: Mapping[str, object]) -> dict[str, object]:
    """Build deadline/lead-aware quest runtime metadata."""

    quests = tuple(_quest(item) for item in _sequence(turn_result.get("quests")) if isinstance(item, Mapping))
    leads = tuple(_lead(item) for item in _sequence(turn_result.get("leads")) if isinstance(item, Mapping))
    turn = int(turn_result.get("turn") or turn_result.get("turn_index") or 0)
    converted = tuple(_lead_to_quest(lead) for lead in leads if lead.status in ("rumor", "lead"))
    all_quests = quests + converted
    deadlines = [_deadline_payload(raw, turn) for raw in _sequence(turn_result.get("deadlines")) if isinstance(raw, Mapping)]
    expired = {str(item["quest_id"]) for item in deadlines if item.get("status") == "expired"}
    journal = chronicle_payload((), all_quests)
    issues = tuple(_quest_issues(all_quests, leads, deadlines))
    return {
        "source": QUEST_RUNTIME_SOURCE,
        "ready": not issues,
        "issues": list(issues),
        "turn": turn,
        "leads": [lead.as_dict() for lead in leads],
        "converted_quests": [quest.as_dict() for quest in converted],
        "deadlines": deadlines,
        "expired_quest_ids": sorted(expired),
        "journal": journal,
    }


def _lead_to_quest(lead: QuestLead) -> QuestState:
    quest = rumor_to_quest(lead.lead_id, lead.summary, clue=lead.clue, location_id=lead.location_id or None)
    if lead.npc_id:
        quest = QuestState(
            quest.quest_id,
            quest.title,
            quest.status,
            objectives=(QuestObjective(f"follow-{lead.lead_id}", f"Follow lead: {lead.clue}"),),
            known_clues=quest.known_clues,
            npc_ids=(lead.npc_id,),
            location_ids=quest.location_ids,
        )
    return quest


def _deadline_payload(raw: Mapping[str, object], turn: int) -> dict[str, object]:
    due_turn = raw.get("due_turn")
    if not isinstance(due_turn, int):
        status: DeadlineStatus = "none"
    elif turn > due_turn:
        status = "expired"
    elif turn == due_turn:
        status = "due_now"
    else:
        status = "active"
    return {
        "quest_id": str(raw.get("quest_id") or ""),
        "due_turn": due_turn,
        "turns_remaining": due_turn - turn if isinstance(due_turn, int) else None,
        "status": status,
    }


def _quest(raw: Mapping[str, object]) -> QuestState:
    objectives = tuple(
        QuestObjective(str(item.get("objective_id") or item.get("id") or "objective"), str(item.get("summary") or ""), bool(item.get("complete", False)))
        for item in _sequence(raw.get("objectives"))
        if isinstance(item, Mapping)
    )
    return QuestState(
        quest_id=str(raw.get("quest_id") or raw.get("id") or "quest"),
        title=str(raw.get("title") or "Quest"),
        status=str(raw.get("status") or "unknown"),  # type: ignore[arg-type]
        objectives=objectives,
        known_clues=tuple(str(item) for item in _sequence(raw.get("known_clues"))),
        npc_ids=tuple(str(item) for item in _sequence(raw.get("npc_ids"))),
        location_ids=tuple(str(item) for item in _sequence(raw.get("location_ids"))),
        reward=str(raw.get("reward") or ""),
        risk=str(raw.get("risk") or ""),
    )


def _lead(raw: Mapping[str, object]) -> QuestLead:
    return QuestLead(
        lead_id=str(raw.get("lead_id") or raw.get("id") or "lead"),
        summary=str(raw.get("summary") or raw.get("title") or "Lead"),
        clue=str(raw.get("clue") or raw.get("summary") or ""),
        location_id=str(raw.get("location_id") or ""),
        npc_id=str(raw.get("npc_id") or ""),
        status=str(raw.get("status") or "lead"),  # type: ignore[arg-type]
    )


def _quest_issues(
    quests: Sequence[QuestState],
    leads: Sequence[QuestLead],
    deadlines: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    issues: list[str] = []
    if not quests and not leads:
        issues.append("missing_quest_or_lead")
    quest_ids = {quest.quest_id for quest in quests} | {lead.lead_id for lead in leads}
    for deadline in deadlines:
        quest_id = str(deadline.get("quest_id") or "")
        if quest_id and quest_id not in quest_ids:
            issues.append(f"deadline_unknown_quest:{quest_id}")
    return tuple(issues)


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()
