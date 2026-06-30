from __future__ import annotations

from app.assist_core.hermes_adapter_contract import hermes_adapter_preview_payload


def test_hermes_adapter_preview_uses_router_policy_for_rpg() -> None:
    payload = hermes_adapter_preview_payload(
        {
            "mode": "rpg",
            "intent": "suggest_next_action",
            "context": {"session_id": "session-1", "location": "Rusty Flagon Tavern"},
        }
    )

    assert payload["ok"] is True
    assert payload["source"] == "hermes_adapter"
    assert payload["mode"] == "rpg"
    assert payload["intent"] == "suggest_next_action"
    assert payload["route"]["hermes_role"] == "suggest"
    assert payload["route"]["execution_owner"] == "rpg_sim"
    assert payload["response_contract"] == {
        "kind": "suggest",
        "items": [],
        "review_required": False,
        "owner": "rpg_sim",
    }


def test_hermes_adapter_preview_handles_missing_and_unknown_mode() -> None:
    assert hermes_adapter_preview_payload({}) == {"ok": False, "error": "missing_mode", "source": "hermes_adapter"}
    assert hermes_adapter_preview_payload({"mode": "unknown"}) == {
        "ok": False,
        "error": "unknown_mode",
        "mode": "unknown",
        "source": "hermes_adapter",
    }
