"""Normalize player-facing merchant commands into deterministic service actions."""
from __future__ import annotations

from typing import Any

from app.rpg.session.item_merchant_service import build_item_merchant_menu, apply_item_merchant_selection

MERCHANT_COMMAND_SOURCE = "engine_item_merchant_commands_v1"
MENU_WORDS = {"shop", "store", "merchant", "menu", "wares", "catalog", "browse"}
BUY_WORDS = {"buy", "purchase"}
SELL_WORDS = {"sell"}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, *, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _norm(value: Any) -> str:
    return _safe_str(value).casefold()


def _quantity_and_item(words: list[str]) -> tuple[int, str | None]:
    if not words:
        return 1, None
    first = words[0]
    if first.isdigit():
        quantity = max(1, int(first))
        return quantity, " ".join(words[1:]).strip() or None
    return 1, " ".join(words).strip() or None


def build_item_merchant_command_plan(command: Any, *, default_profile: str = "general_store") -> dict[str, Any]:
    """Build a deterministic merchant command plan without mutating state."""

    if isinstance(command, dict):
        payload = _safe_dict(command)
        action = _norm(payload.get("merchant_action") or payload.get("action") or payload.get("kind"))
        if action in {"menu", "browse", "shop", "catalog"}:
            return {
                "ok": True,
                "handled": True,
                "service_action": "menu",
                "merchant_profile": _safe_str(payload.get("merchant_profile") or payload.get("profile") or default_profile),
                "record_trace": bool(payload.get("record_trace", True)),
                "mechanics_source": MERCHANT_COMMAND_SOURCE,
            }
        if action in {"buy", "sell"}:
            item_id = _safe_str(payload.get("item_id") or payload.get("item_name") or payload.get("item"))
            return {
                "ok": True,
                "handled": bool(item_id),
                "service_action": action,
                "merchant_profile": _safe_str(payload.get("merchant_profile") or payload.get("profile") or default_profile),
                "item_id": item_id or None,
                "quantity": max(1, _safe_int(payload.get("quantity"), default=1)),
                "record_trace": bool(payload.get("record_trace", True)),
                "mechanics_source": MERCHANT_COMMAND_SOURCE,
            }
        return {"ok": True, "handled": False, "reason": "unsupported_merchant_command", "mechanics_source": MERCHANT_COMMAND_SOURCE}

    text = _safe_str(command)
    if not text:
        return {"ok": True, "handled": False, "reason": "empty_command", "mechanics_source": MERCHANT_COMMAND_SOURCE}
    words = text.split()
    verb = _norm(words[0])
    if verb in MENU_WORDS:
        return {
            "ok": True,
            "handled": True,
            "service_action": "menu",
            "merchant_profile": default_profile,
            "record_trace": True,
            "mechanics_source": MERCHANT_COMMAND_SOURCE,
        }
    if verb in BUY_WORDS | SELL_WORDS:
        quantity, item_id = _quantity_and_item(words[1:])
        return {
            "ok": True,
            "handled": bool(item_id),
            "service_action": "buy" if verb in BUY_WORDS else "sell",
            "merchant_profile": default_profile,
            "item_id": item_id,
            "quantity": quantity,
            "record_trace": True,
            "mechanics_source": MERCHANT_COMMAND_SOURCE,
        }
    return {"ok": True, "handled": False, "reason": "non_merchant_command", "mechanics_source": MERCHANT_COMMAND_SOURCE}


def apply_item_merchant_command(
    state: dict[str, Any],
    command: Any,
    *,
    default_profile: str = "general_store",
    genre: str | None = None,
    level: int | None = None,
    reputation: int | None = None,
) -> dict[str, Any]:
    """Apply a normalized merchant command to mutable session state."""

    plan = build_item_merchant_command_plan(command, default_profile=default_profile)
    if plan.get("handled") is not True:
        return {"ok": True, "handled": False, "skipped": True, "plan": plan, "mechanics_source": MERCHANT_COMMAND_SOURCE}
    profile = _safe_str(plan.get("merchant_profile") or default_profile)
    service_action = _safe_str(plan.get("service_action"))
    record_trace = bool(plan.get("record_trace", True))
    if service_action == "menu":
        menu = build_item_merchant_menu(
            state,
            merchant_profile=profile,
            genre=genre,
            level=level,
            reputation=reputation,
            record_trace=record_trace,
        )
        return {"ok": menu.get("ok") is True, "handled": True, "plan": plan, "menu": menu, "mechanics_source": MERCHANT_COMMAND_SOURCE}
    result = apply_item_merchant_selection(
        state,
        _safe_str(plan.get("item_id")),
        action=service_action,
        quantity=max(1, _safe_int(plan.get("quantity"), default=1)),
        merchant_profile=profile,
        genre=genre,
        level=level,
        reputation=reputation,
        record_trace=record_trace,
    )
    return {"ok": result.get("ok") is True, "handled": True, "plan": plan, "result": result, "mechanics_source": MERCHANT_COMMAND_SOURCE}
