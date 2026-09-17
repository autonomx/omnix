from __future__ import annotations

"""Typed provider-binding purpose and execution-authority guards."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


BindingPurpose = Literal["LIVE_DATA", "EXECUTION", "REPLAY", "RESEARCH"]


def infer_binding_purpose(binding_id: str | None) -> BindingPurpose:
    """Classify legacy binding IDs conservatively by their durable prefix.

    Existing production execution bindings predate an explicit purpose field, so
    non-special bindings remain EXECUTION for compatibility. Replay/research
    prefixes are fail-closed and can never become execution authority.
    """

    value = str(binding_id or "").strip().casefold()
    if value.startswith("replay:"):
        return "REPLAY"
    if value.startswith("research:"):
        return "RESEARCH"
    if value.startswith("live:"):
        return "LIVE_DATA"
    return "EXECUTION"


class PurposeBoundBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str = Field(min_length=1, max_length=240)
    purpose: BindingPurpose

    @model_validator(mode="after")
    def _prefix_consistent(self):
        inferred = infer_binding_purpose(self.binding_id)
        if inferred in {"REPLAY", "RESEARCH"} and inferred != self.purpose:
            raise ValueError("binding_purpose_conflicts_with_binding_id")
        return self


def require_execution_binding(
    binding_id: str | None,
    *,
    purpose: BindingPurpose | None = None,
) -> str | None:
    if binding_id is None:
        return None
    resolved = purpose or infer_binding_purpose(binding_id)
    if resolved != "EXECUTION":
        raise ValueError(f"execution_binding_purpose_invalid:{resolved}")
    return binding_id


def binding_can_execute(
    binding_id: str | None,
    *,
    purpose: BindingPurpose | None = None,
) -> bool:
    try:
        require_execution_binding(binding_id, purpose=purpose)
    except ValueError:
        return False
    return True


__all__ = [
    "BindingPurpose",
    "PurposeBoundBinding",
    "binding_can_execute",
    "infer_binding_purpose",
    "require_execution_binding",
]
