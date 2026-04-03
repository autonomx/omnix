from __future__ import annotations

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


@dataclass
class RetconDirective(GMDirective):
    subject: str = ""
    predicate: str = ""
    value: Any = None


@dataclass
class CanonOverrideDirective(GMDirective):
    fact_id: str = ""
    value: Any = None


@dataclass
class PacingDirective(GMDirective):
    style: str = "balanced"


@dataclass
class ToneDirective(GMDirective):
    tone: str = "neutral"


@dataclass
class DangerDirective(GMDirective):
    level: str = "medium"


DIRECTIVE_TYPES = {
    "inject_event": InjectEventDirective,
    "pin_thread": PinThreadDirective,
    "retcon": RetconDirective,
    "canon_override": CanonOverrideDirective,
    "pacing": PacingDirective,
    "tone": ToneDirective,
    "danger": DangerDirective,
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
                coherence_core.upsert_fact(
                    FactRecord(
                        fact_id=directive.fact_id,
                        category="world",
                        subject=directive.fact_id.split(":", 1)[0] if ":" in directive.fact_id else directive.fact_id,
                        predicate="override",
                        value=directive.value,
                        authority="creator_canon",
                        status="confirmed",
                        metadata={"directive_id": directive.directive_id, **directive.metadata},
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
