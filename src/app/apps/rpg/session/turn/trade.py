"""Trade on the pipeline (RQ-2.3): the economy's trade rule (``rules/economy/trade.py``) says what buying or selling
does; this adapts its outcome to the turn (counted, ten minutes, its lines for the narrator)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d
from app.apps.rpg.foundation.state.changes import StateChange, TimeAdvanced, TurnCounted
from app.apps.rpg.rules.economy.trade import buy, sell
from app.apps.rpg.foundation.state import access as _sections

MINUTES_PER_TICK = 10


@dataclass(frozen=True)
class TradeResolution:
    changes: list[StateChange]
    lines: list[str]
    refused: bool = False
    minutes: int = MINUTES_PER_TICK
    kind: str = ""


def resolve_trade(document: Mapping[str, Any], text: str, *, selling: bool = False) -> TradeResolution | None:
    """The trade the player asks for, or ``None`` in a world without an economy section (the older path's)."""
    simulation = _d(_sections.simulation_state_of(document))
    outcome = sell(simulation, text) if selling else buy(simulation, text)
    if outcome is None:
        return None
    state, manifest = _d(document.get("state")), _d(document.get("manifest"))
    counted = TurnCounted(turn_count=int(state.get("turn_count") or manifest.get("turn_count") or 0) + 1)
    return TradeResolution([counted, TimeAdvanced(ticks=1, minutes=MINUTES_PER_TICK), *outcome.changes],
                           outcome.lines, refused=outcome.refused, kind=outcome.kind)


__all__ = ["TradeResolution", "resolve_trade"]
