"""Deterministic special item signal helpers for RPG sessions."""
from __future__ import annotations


from copy import deepcopy
from typing import Any

from app.apps.rpg.session.inventory_items import item_type
from app.apps.rpg.foundation.safe_values import safe_dict as _safe_dict, safe_list as _safe_list

SUPPORTED_SIGNAL_OPS = {"add_affordance", "add_scene_status", "set_world_flag", "restore_resource"}
AFFORDANCE_BUCKETS = {"dialogue", "travel", "access", "evidence", "crafting", "combat", "social"}
RESOURCES = {"hp", "mana", "stamina"}


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _norm(value: Any) -> str:
    return _text(value).casefold()


def _positive_int(value: Any, fallback: int = 1, *, limit: int = 250) -> int:
    try:
        return max(1, min(limit, int(value)))
    except Exception:
        return fallback


def _signal_id(signal: dict[str, Any], ordinal: int) -> str:
    return _text(signal.get("signal_id") or signal.get("id") or signal.get("name"), f"item_signal_{ordinal + 1}")


def is_signal_item(item: dict[str, Any]) -> bool:
    normalized_type = _norm(item_type(item))
    tags = {_norm(tag) for tag in _safe_list(item.get("tags")) if _text(tag)}
    return normalized_type in {"artifact", "quest", "quest_item", "relic", "key"} or bool(tags & {"artifact", "relic", "quest", "signal"})


def _raw_signals(item: dict[str, Any]) -> list[Any]:
    for key in ("item_signals", "artifact_powers", "quest_powers", "powers"):
        raw = item.get(key)
        if isinstance(raw, list):
            return raw
    return []


def normalize_item_signals(item: dict[str, Any]) -> dict[str, Any]:
    repairs: list[str] = []
    signals: list[dict[str, Any]] = []
    if not is_signal_item(item):
        return {"ok": False, "error": "item_has_no_signal_contract", "signals": [], "repairs": []}

    for ordinal, raw_signal in enumerate(_raw_signals(item)):
        signal = deepcopy(_safe_dict(raw_signal))
        op = _norm(signal.get("op") or signal.get("operation") or signal.get("type"))
        if op not in SUPPORTED_SIGNAL_OPS:
            repairs.append(f"ignored_unsupported_item_signal_op:{op or ordinal}")
            continue
        signal_id = _signal_id(signal, ordinal)
        normalized = {"signal_id": signal_id, "op": op, "consume": signal.get("consume") is True}
        if op == "add_affordance":
            bucket = _norm(signal.get("bucket") or signal.get("kind")) or "dialogue"
            if bucket not in AFFORDANCE_BUCKETS:
                repairs.append(f"repaired_affordance_bucket:{bucket}")
                bucket = "dialogue"
            tag = _text(signal.get("tag") or signal.get("affordance"))
            if not tag:
                repairs.append(f"ignored_item_signal_affordance_without_tag:{ordinal}")
                continue
            normalized.update({"bucket": bucket, "tag": tag[:80], "dimension": _text(signal.get("dimension"), "item")[:40]})
        elif op == "add_scene_status":
            status = _text(signal.get("status") or signal.get("tag"))
            if not status:
                repairs.append(f"ignored_item_signal_status_without_status:{ordinal}")
                continue
            normalized.update({"status": status[:80], "dimension": _text(signal.get("dimension"), "item")[:40]})
        elif op == "set_world_flag":
            flag = _text(signal.get("flag") or signal.get("key"))
            if not flag:
                repairs.append(f"ignored_item_signal_flag_without_key:{ordinal}")
                continue
            normalized.update({"flag": flag[:80], "value": signal.get("value", True)})
        elif op == "restore_resource":
            resource = _norm(signal.get("resource") or signal.get("stat"))
            if resource not in RESOURCES:
                repairs.append(f"ignored_item_signal_restore_without_supported_resource:{ordinal}")
                continue
            normalized.update({"resource": resource, "amount": _positive_int(signal.get("amount") or signal.get("delta"), 1)})
        signals.append(normalized)

    if not signals:
        return {"ok": False, "error": "no_supported_item_signals", "signals": [], "repairs": repairs}
    return {"ok": True, "signals": signals, "repairs": repairs}
