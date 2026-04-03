from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GMDirective:
    directive_id: str
    directive_type: str
    scope: str = "global"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GMDirective":
        return cls(**data)


@dataclass
class InjectEventDirective(GMDirective):
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PinThreadDirective(GMDirective):
    thread_id: str = ""
    priority: str = "high"


@dataclass
class RetconDirective(GMDirective):
    subject: str = ""
    predicate: str = ""
    value: Any = None
    reason: str = ""


@dataclass
class CanonOverrideDirective(GMDirective):
    fact_id: str = ""
    subject: str = ""
    predicate: str = ""
    value: Any = None
    reason: str = ""


@dataclass
class PacingDirective(GMDirective):
    style: str = "balanced"


@dataclass
class ToneDirective(GMDirective):
    tone: str = "neutral"
    target_scope: str = "scene"


@dataclass
class DangerDirective(GMDirective):
    level: str = "medium"
    target_scope: str = "scene"


@dataclass
class TargetNPCDirective(GMDirective):
    npc_id: str = ""
    instruction: str = ""


@dataclass
class TargetFactionDirective(GMDirective):
    faction_id: str = ""
    instruction: str = ""


@dataclass
class TargetLocationDirective(GMDirective):
    location_id: str = ""
    instruction: str = ""


@dataclass
class RevealDirective(GMDirective):
    reveal_type: str = ""
    target_id: str = ""
    timing: str = "soon"


DIRECTIVE_TYPES = {
    "inject_event": InjectEventDirective,
    "pin_thread": PinThreadDirective,
    "retcon": RetconDirective,
    "canon_override": CanonOverrideDirective,
    "pacing": PacingDirective,
    "tone": ToneDirective,
    "danger": DangerDirective,
    "target_npc": TargetNPCDirective,
    "target_faction": TargetFactionDirective,
    "target_location": TargetLocationDirective,
    "reveal": RevealDirective,
}


class GMDirectiveState:
    def __init__(self) -> None:
        self.directives: dict[str, GMDirective] = {}

    def add_directive(self, directive: GMDirective) -> None:
        self.directives[directive.directive_id] = directive

    def remove_directive(self, directive_id: str) -> None:
        self.directives.pop(directive_id, None)

    def clear_scene_scoped_directives(self) -> None:
        self.directives = {
            k: v for k, v in self.directives.items() if v.scope != "scene"
        }

    def list_directives(self) -> list[GMDirective]:
        return list(self.directives.values())

    def get_active_directives(self) -> list[GMDirective]:
        return [d for d in self.directives.values() if d.enabled]

    def get_pending_injected_events(self) -> list[dict]:
        """Return deterministic event payloads for active inject-event directives.

        The GameLoop is responsible for actually emitting these into the EventBus.
        Returned items include directive identity and scope so the loop can
        clear only successfully emitted scene-scoped directives.
        """
        events: list[dict] = []
        for directive in self.get_active_directives():
            if isinstance(directive, InjectEventDirective):
                events.append(
                    {
                        "directive_id": directive.directive_id,
                        "scope": directive.scope,
                        "event_type": directive.event_type,
                        "payload": copy.deepcopy(directive.payload),
                    }
                )
        return events

    def remove_directives(self, directive_ids: list[str]) -> None:
        """Remove a specific set of directives by id."""
        for directive_id in directive_ids:
            self.directives.pop(directive_id, None)

    def apply_to_coherence(self, coherence_core: Any) -> None:
        from ..coherence.models import FactRecord

        for directive in self.get_active_directives():
            if isinstance(directive, RetconDirective):
                coherence_core.upsert_fact(
                    FactRecord(
                        fact_id=f"gm_retcon:{directive.directive_id}",
                        category="world",
                        subject=directive.subject,
                        predicate=directive.predicate,
                        value=directive.value,
                        authority="creator_canon",
                        status="confirmed",
                        metadata={"directive_id": directive.directive_id, **directive.metadata},
                    )
                )
            elif isinstance(directive, CanonOverrideDirective):
                subject = directive.subject or (
                    directive.fact_id.split(":", 1)[0] if ":" in directive.fact_id else directive.fact_id
                )
                predicate = directive.predicate or (
                    directive.fact_id.split(":", 1)[1] if ":" in directive.fact_id else "value"
                )
                coherence_core.upsert_fact(
                    FactRecord(
                        fact_id=directive.fact_id,
                        category="world",
                        subject=subject,
                        predicate=predicate,
                        value=directive.value,
                        authority="creator_canon",
                        status="confirmed",
                        metadata={
                            "directive_id": directive.directive_id,
                            "directive_type": "canon_override",
                            **directive.metadata,
                        },
                    )
                )

    def build_director_context(self) -> dict:
        active = self.get_active_directives()
        return {
            "active_directives": [self._directive_to_dict(d) for d in active],
            "pacing": [d.style for d in active if isinstance(d, PacingDirective)],
            "tone": [d.tone for d in active if isinstance(d, ToneDirective)],
            "danger": [d.level for d in active if isinstance(d, DangerDirective)],
            "pinned_threads": [d.thread_id for d in active if isinstance(d, PinThreadDirective)],
        }

    # ------------------------------------------------------------------
    # Entity-targeted query helpers (Phase 7.1)
    # ------------------------------------------------------------------

    def find_directives_for_npc(self, npc_id: str) -> list[GMDirective]:
        """Return all active directives that target a specific NPC."""
        results: list[GMDirective] = []
        for d in self.get_active_directives():
            if isinstance(d, TargetNPCDirective) and d.npc_id == npc_id:
                results.append(d)
            elif isinstance(d, RevealDirective) and d.target_id == npc_id:
                results.append(d)
        return results

    def find_directives_for_faction(self, faction_id: str) -> list[GMDirective]:
        """Return all active directives that target a specific faction."""
        results: list[GMDirective] = []
        for d in self.get_active_directives():
            if isinstance(d, TargetFactionDirective) and d.faction_id == faction_id:
                results.append(d)
            elif isinstance(d, RevealDirective) and d.target_id == faction_id:
                results.append(d)
        return results

    def find_directives_for_location(self, location_id: str) -> list[GMDirective]:
        """Return all active directives that target a specific location."""
        results: list[GMDirective] = []
        for d in self.get_active_directives():
            if isinstance(d, TargetLocationDirective) and d.location_id == location_id:
                results.append(d)
            elif isinstance(d, RevealDirective) and d.target_id == location_id:
                results.append(d)
        return results

    def build_ui_summary(self) -> dict:
        """Return a UI-friendly summary of the current directive state."""
        active = self.get_active_directives()
        by_type: dict[str, list[dict]] = {}
        for d in active:
            dtype = d.directive_type
            if dtype not in by_type:
                by_type[dtype] = []
            by_type[dtype].append(self._directive_to_dict(d))
        return {
            "total_directives": len(self.directives),
            "active_directives": len(active),
            "by_type": by_type,
        }

    def serialize_state(self) -> dict:
        return {
            "directives": {
                k: self._directive_to_dict(v) for k, v in self.directives.items()
            }
        }

    def deserialize_state(self, data: dict) -> None:
        self.directives = {}
        for directive_id, payload in data.get("directives", {}).items():
            cls = DIRECTIVE_TYPES.get(payload.get("directive_type"), GMDirective)
            self.directives[directive_id] = cls(**payload)

    def _directive_to_dict(self, directive: GMDirective) -> dict:
        return asdict(directive)
