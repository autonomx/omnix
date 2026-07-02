from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hermes_sequence_contract import hermes_sequence_contract_validate

StepSubmitter = Callable[[dict[str, Any]], dict[str, Any]]


def _next_index(items: list[dict[str, Any]]) -> int | None:
    for index, item in enumerate(items):
        if item.get("status") not in {"done", "blocked"}:
            return index
    return None


def _with_item_status(sequence: dict[str, Any], index: int, status: str) -> dict[str, Any]:
    updated = dict(sequence)
    updated["items"] = [dict(item) for item in sequence.get("items", [])]
    updated["items"][index]["status"] = status
    return updated


def hermes_sequence_step_once(raw: dict[str, Any], submitter: StepSubmitter) -> dict[str, Any]:
    checked = hermes_sequence_contract_validate(raw)
    if not checked["ok"]:
        return {
            "ok": False,
            "source": "hermes_sequence_stepper",
            "status": "blocked",
            "errors": checked["errors"],
            "sequence": checked["sequence"],
            "state_changed": False,
        }

    sequence = checked["sequence"]
    items = sequence["items"]
    index = _next_index(items)
    if index is None:
        return {
            "ok": True,
            "source": "hermes_sequence_stepper",
            "status": "complete",
            "sequence": sequence,
            "state_changed": False,
        }

    item = items[index]
    if item.get("user_gate") is True and item.get("status") == "pending":
        return {
            "ok": False,
            "source": "hermes_sequence_stepper",
            "status": "needs_review",
            "item_index": index,
            "item": item,
            "sequence": sequence,
            "state_changed": False,
        }

    result = submitter({
        "sequence_id": sequence["sequence_id"],
        "item_id": item["item_id"],
        "statement": item["statement"],
        "domain": sequence["domain"],
        "state_owner": sequence["state_owner"],
    })
    succeeded = result.get("ok") is True
    updated = _with_item_status(sequence, index, "done" if succeeded else "blocked")
    return {
        "ok": succeeded,
        "source": "hermes_sequence_stepper",
        "status": "advanced" if succeeded else "blocked",
        "item_index": index,
        "item": updated["items"][index],
        "result": result,
        "sequence": updated,
        "state_changed": succeeded,
    }
