"""Deterministic social scene and NPC speaking gate helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

ConversationKind = Literal["directed", "ambient", "group", "argument", "negotiation", "interrogation", "party_banter"]
MemoryHookKind = Literal["promise", "threat", "secret", "deal", "insult", "clue"]


@dataclass(frozen=True)
class SocialThread:
    thread_id: str
    kind: ConversationKind
    participants: tuple[str, ...]
    active: bool = True
    ambient_budget: int = 0
    last_speaker_id: str | None = None

    def includes(self, npc_id: str) -> bool:
        return npc_id in self.participants

    def with_speaker(self, npc_id: str) -> "SocialThread":
        next_budget = max(0, self.ambient_budget - 1) if self.kind == "ambient" else self.ambient_budget
        return replace(self, last_speaker_id=npc_id, ambient_budget=next_budget)


@dataclass(frozen=True)
class SocialSpeakRequest:
    npc_id: str
    thread_id: str
    directly_addressed: bool = False
    urgent_reaction: bool = False
    relationship_trigger: bool = False
    player_is_leaving: bool = False


@dataclass(frozen=True)
class SocialSpeakDecision:
    npc_id: str
    thread_id: str
    allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"npc_id": self.npc_id, "thread_id": self.thread_id, "allowed": self.allowed, "reason": self.reason}


@dataclass(frozen=True)
class SocialMemoryHook:
    hook_id: str
    kind: MemoryHookKind
    npc_ids: tuple[str, ...]
    fact: str
    source_event_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "hook_id": self.hook_id,
            "kind": self.kind,
            "npc_ids": list(self.npc_ids),
            "fact": self.fact,
            "source_event_id": self.source_event_id,
        }


def decide_npc_speaks(thread: SocialThread, request: SocialSpeakRequest) -> SocialSpeakDecision:
    if not thread.active:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, False, "thread_inactive")
    if request.thread_id != thread.thread_id:
        return SocialSpeakDecision(request.npc_id, request.thread_id, False, "thread_mismatch")
    if not thread.includes(request.npc_id):
        return SocialSpeakDecision(request.npc_id, thread.thread_id, False, "npc_not_in_thread")
    if request.player_is_leaving and not request.urgent_reaction:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, False, "player_leaving")
    if thread.last_speaker_id == request.npc_id and not request.directly_addressed:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, False, "repeat_speaker_blocked")
    if request.directly_addressed:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, True, "directly_addressed")
    if request.urgent_reaction:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, True, "urgent_reaction")
    if request.relationship_trigger:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, True, "relationship_trigger")
    if thread.kind == "ambient" and thread.ambient_budget <= 0:
        return SocialSpeakDecision(request.npc_id, thread.thread_id, False, "ambient_budget_empty")
    return SocialSpeakDecision(request.npc_id, thread.thread_id, True, "scene_participant")


def apply_speak_decision(thread: SocialThread, decision: SocialSpeakDecision) -> SocialThread:
    if not decision.allowed:
        return thread
    return thread.with_speaker(decision.npc_id)


def build_memory_hook(
    kind: MemoryHookKind,
    *,
    source_event_id: str,
    npc_ids: Sequence[str],
    fact: str,
) -> SocialMemoryHook:
    hook_id = f"social:{source_event_id}:{kind}"
    return SocialMemoryHook(hook_id, kind, tuple(sorted(set(npc_ids))), fact.strip(), source_event_id)


def social_scene_report(thread: SocialThread, decisions: Sequence[SocialSpeakDecision]) -> dict[str, object]:
    return {
        "thread_id": thread.thread_id,
        "kind": thread.kind,
        "participants": list(thread.participants),
        "active": thread.active,
        "ambient_budget": thread.ambient_budget,
        "last_speaker_id": thread.last_speaker_id,
        "decisions": [decision.as_dict() for decision in decisions],
    }
