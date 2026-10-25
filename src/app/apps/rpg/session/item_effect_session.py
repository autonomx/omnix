"""Session bridge for deterministic item effects."""
from __future__ import annotations


from typing import Any

from app.apps.rpg.session.inventory_items import display_item_name
from app.apps.rpg.session.item_signals import normalize_item_signals
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def available_item_effects_for_session(state: dict[str, Any], player: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    player = _safe_dict(player or _safe_dict(state).get("player"))
    summaries: list[dict[str, Any]] = []
    for raw_item in _safe_list(player.get("inventory")):
        item = _safe_dict(raw_item)
        if not item:
            continue
        normalized = normalize_item_signals(item)
        if not normalized.get("ok"):
            continue
        summaries.append(
            {
                "item_id": _text(item.get("item_id") or item.get("id")),
                "name": display_item_name(item),
                "effects": [
                    {
                        "id": _text(_safe_dict(signal).get("signal_id")),
                        "op": _text(_safe_dict(signal).get("op")),
                        "consume": _safe_dict(signal).get("consume") is True,
                    }
                    for signal in _safe_list(normalized.get("signals"))
                ],
                "repairs": list(normalized.get("repairs") or []),
            }
        )
    return summaries
