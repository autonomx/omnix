from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import item_detail, service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "location": "Ashen Crossroads Inn",
            "metadata": {
                "genre": "deterministic_rpg_campaign",
                "campaign_template": "deterministic_rpg_campaign",
                "tone": "Grounded frontier fantasy",
                "origin": "frontier_village",
                "starter_gear": ["Field Kit", "Iron dagger", "10 silver"],
            },
            "character_identity": {
                "background": "wanderer",
                "power_source": "mundane",
            },
            "player": {
                "inventory": [
                    {
                        "item_id": "field_kit",
                        "name": "Field Kit",
                        "item_type": "tool",
                        "quantity": 2,
                        "durability": {"current": 4, "max": 10},
                        "tags": ["survival"],
                    }
                ]
            },
        },
    }


class _Gateway:
    def __init__(self) -> None:
        self.context: dict[str, Any] = {}

    def generate(self, prompt: str, *, context: dict[str, Any], timeout_s: float) -> str:
        assert "exactly three sentences" in prompt
        assert "do not invent unique provenance" in prompt
        assert "Do not mention inventory quantity" in prompt
        assert timeout_s == 20.0
        self.context = context
        return (
            "A weathered leather case reinforced with dull brass corners, its surface marked by rain and road dust. "
            "Inside, fitted loops hold the simple tools needed for repairs far from a settled workshop. "
            "Kits like this are common among frontier scouts, caravan hands, and wandering tradespeople."
        )


def test_item_detail_compat_generates_prose_from_read_only_item_facts(monkeypatch) -> None:
    session = _session()
    before = deepcopy(session)
    gateway = _Gateway()

    monkeypatch.setattr(service, "load_session", lambda session_id: session)
    monkeypatch.setattr(item_detail, "build_app_llm_gateway", lambda: gateway)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_detail", "session_id": "rpg_test", "item_name": "Field Kit"}
    )

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert result["item_detail"] == {
        "item_name": "Field Kit",
        "summary": (
            "A weathered leather case reinforced with dull brass corners, its surface marked by rain and road dust. "
            "Inside, fitted loops hold the simple tools needed for repairs far from a settled workshop. "
            "Kits like this are common among frontier scouts, caravan hands, and wandering tradespeople."
        ),
        "status": "Carried",
        "condition": "Worn (40%)",
        "item_type": "Tool",
        "quantity": 2,
        "tags": ["Tool", "survival"],
        "source": "llm",
    }
    assert gateway.context["setting"] == {
        "genre": "classic_fantasy",
        "campaign_template": "deterministic_rpg_campaign",
        "tone": "Grounded frontier fantasy",
        "location": "Ashen Crossroads Inn",
        "origin": "frontier_village",
        "character_background": "wanderer",
        "power_source": "mundane",
        "opening_hook": "",
        "climate_profile": "",
        "starter_gear": ["Field Kit", "Iron dagger", "10 silver"],
    }
    assert gateway.context["item"] == {
        "name": "Field Kit",
        "item_type": "Tool",
        "tags": ["Tool", "survival"],
    }
    assert session == before


def test_item_detail_compat_reports_provider_unavailable_instead_of_pending(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(item_detail, "build_app_llm_gateway", lambda: None)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_detail", "session_id": "rpg_test", "item_name": "Field Kit"}
    )

    assert result["ok"] is False
    assert result["error"] == "item_detail_llm_unavailable"
    assert result["item_detail"]["source"] == "unavailable"
    assert result["item_detail"]["status"] == "Carried"
    assert result["item_detail"]["condition"] == "Worn (40%)"


def test_item_detail_compat_requires_session_and_item_names() -> None:
    assert rpg_session_compat.get_rpg_session_payload({"action": "item_detail"}) == {
        "ok": False,
        "error": "missing_session_id",
    }
