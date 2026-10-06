from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .binding_authority import BindingPurpose, binding_can_execute, infer_binding_purpose


PaperProtectionStatus = Literal[
    "pending_entry",
    "active",
    "exit_submitted",
    "closed",
    "cancelled",
    "quarantined",
]


class PaperProtectionUpsert(BaseModel):
    """Server-authoritative OCO-style stop/target protection for a paper position."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    entry_order_id: str | None = Field(default=None, max_length=200)
    take_profit: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_level(self):
        if self.binding_id is not None and not binding_can_execute(self.binding_id):
            raise ValueError("paper_protection_requires_execution_binding")
        if self.take_profit is None and self.stop_loss is None:
            raise ValueError("paper protection requires take_profit or stop_loss")
        if (
            self.take_profit is not None
            and self.stop_loss is not None
            and self.take_profit == self.stop_loss
        ):
            raise ValueError("take_profit and stop_loss must differ")
        return self


class PaperPositionProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    instrument_id: str
    binding_id: str | None = None
    binding_purpose: BindingPurpose = "EXECUTION"
    entry_order_id: str | None = None
    exit_order_id: str | None = None
    take_profit: Decimal | None = None
    stop_loss: Decimal | None = None
    status: PaperProtectionStatus
    trigger_reason: str | None = None
    revision: int = Field(default=1, ge=1)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def binding_authority_consistent(self):
        inferred = infer_binding_purpose(self.binding_id)
        if self.status in {"pending_entry", "active", "exit_submitted"} and (
            self.binding_purpose != "EXECUTION" or inferred != "EXECUTION"
        ):
            raise ValueError("active_paper_protection_requires_execution_binding")
        return self
