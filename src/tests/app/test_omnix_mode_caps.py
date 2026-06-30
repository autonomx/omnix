from __future__ import annotations

from app.assist_core.omnix_mode_policy import list_omnix_mode_policies, omnix_mode_policy, omnix_mode_policy_payload


def test_omnix_mode_caps_lists_expected_rows() -> None:
    policies = {policy["mode"]: policy for policy in list_omnix_mode_policies()}

    assert policies["normal_chat"]["hermes_capabilities"] == []
    assert policies["live_chat"]["hermes_capabilities"] == ["observe"]
    assert policies["podcast"]["hermes_capabilities"] == ["observe", "critique", "plan"]
    assert policies["rpg"]["hermes_capabilities"] == ["observe", "suggest", "critique"]


def test_omnix_mode_caps_carries_owner_and_review_flag() -> None:
    agent = omnix_mode_policy("agent_mode")
    rpg = omnix_mode_policy("rpg")

    assert agent["requires_review"] is True
    assert agent["owner"] == "omnix"
    assert rpg["requires_review"] is False
    assert rpg["owner"] == "rpg_sim"


def test_omnix_mode_caps_payload_handles_single_and_unknown_modes() -> None:
    assert omnix_mode_policy_payload("podcast") == {"ok": True, "policy": omnix_mode_policy("podcast")}
    assert omnix_mode_policy_payload("unknown") == {"ok": False, "error": "unknown_mode", "mode": "unknown"}
