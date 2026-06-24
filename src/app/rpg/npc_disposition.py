"""Deterministic NPC disposition and relationship-axis helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping

DispositionAxis = Literal[
    "trust",
    "respect",
    "friendship",
    "fear",
    "loyalty",
    "suspicion",
    "romantic_interest",
    "debt",
    "resentment",
]

DISPOSITION_AXES: tuple[DispositionAxis, ...] = (
    "trust",
    "respect",
    "friendship",
    "fear",
    "loyalty",
    "suspicion",
    "romantic_interest",
    "debt",
    "resentment",
)

MIN_DISPOSITION = -100
MAX_DISPOSITION = 100


@dataclass(frozen=True)
class NpcDisposition:
    npc_id: str
    values: Mapping[DispositionAxis, int]

    @classmethod
    def neutral(cls, npc_id: str) -> "NpcDisposition":
        return cls(npc_id=npc_id, values={axis: 0 for axis in DISPOSITION_AXES})

    def value(self, axis: DispositionAxis) -> int:
        return int(self.values.get(axis, 0))

    def as_dict(self) -> dict[str, object]:
        return {"npc_id": self.npc_id, "values": {axis: self.value(axis) for axis in DISPOSITION_AXES}}


@dataclass(frozen=True)
class DispositionDelta:
    npc_id: str
    axis: DispositionAxis
    amount: int
    reason: str
    source_event_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "npc_id": self.npc_id,
            "axis": self.axis,
            "amount": self.amount,
            "reason": self.reason,
            "source_event_id": self.source_event_id,
        }


@dataclass(frozen=True)
class DispositionChangeReport:
    npc_id: str
    before: Mapping[DispositionAxis, int]
    after: Mapping[DispositionAxis, int]
    applied: tuple[DispositionDelta, ...]

    def changed_axes(self) -> tuple[DispositionAxis, ...]:
        return tuple(axis for axis in DISPOSITION_AXES if self.before.get(axis, 0) != self.after.get(axis, 0))

    def as_dict(self) -> dict[str, object]:
        return {
            "npc_id": self.npc_id,
            "before": dict(self.before),
            "after": dict(self.after),
            "changed_axes": list(self.changed_axes()),
            "applied": [delta.as_dict() for delta in self.applied],
        }


def clamp_disposition(value: int) -> int:
    return max(MIN_DISPOSITION, min(MAX_DISPOSITION, int(value)))


def apply_disposition_deltas(
    disposition: NpcDisposition,
    deltas: tuple[DispositionDelta, ...],
) -> tuple[NpcDisposition, DispositionChangeReport]:
    applicable = tuple(delta for delta in deltas if delta.npc_id == disposition.npc_id)
    before = {axis: disposition.value(axis) for axis in DISPOSITION_AXES}
    after = dict(before)
    for delta in applicable:
        after[delta.axis] = clamp_disposition(after.get(delta.axis, 0) + delta.amount)
    updated = replace(disposition, values=after)
    return updated, DispositionChangeReport(disposition.npc_id, before, after, applicable)


def companion_eligible(disposition: NpcDisposition, *, trust: int = 25, loyalty: int = 10, suspicion_max: int = 30) -> bool:
    return (
        disposition.value("trust") >= trust
        and disposition.value("loyalty") >= loyalty
        and disposition.value("suspicion") <= suspicion_max
    )


def price_adjustment_percent(disposition: NpcDisposition) -> int:
    """Return deterministic merchant price adjustment. Negative means discount."""

    trust = disposition.value("trust")
    resentment = disposition.value("resentment")
    fear = disposition.value("fear")
    discount = min(15, max(0, trust // 10))
    surcharge = min(25, max(0, (resentment + fear) // 8))
    return surcharge - discount


def memory_summary_from_disposition(disposition: NpcDisposition) -> str:
    strong = [(axis, disposition.value(axis)) for axis in DISPOSITION_AXES if abs(disposition.value(axis)) >= 10]
    if not strong:
        return f"{disposition.npc_id} has no strong disposition toward the player yet."
    parts = [f"{axis} {value:+d}" for axis, value in strong]
    return f"{disposition.npc_id} disposition toward the player: " + ", ".join(parts) + "."
