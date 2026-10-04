"""RPG services other features read (WP-8.2)."""
from __future__ import annotations

from typing import Any


def hermes_rpg_plan_summary_payload() -> dict[str, Any]:
    """The Hermes RPG plan summary assist mode reads out; loaded on first use."""
    from app.rpg.hermes.plan_summary import hermes_rpg_plan_summary_payload as summary

    return summary()


__all__ = ["hermes_rpg_plan_summary_payload"]
