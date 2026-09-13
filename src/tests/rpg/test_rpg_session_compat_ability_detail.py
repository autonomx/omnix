from copy import deepcopy
from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import ability_detail, service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "location": "Ashen Crossroads Inn",
            "metadata": {"genre": "classic_fantasy", "tone": "Grounded frontier fantasy"},
            "character_identity": {"background": "wanderer", "power_source": "mundane"},
            "ability_tree": {
                "abilities": [
                    {
                        "ability_id": "recon_frost_arrow",
                        "name": "Frost Arrow",
                        "kind": "active",
                        "description": "Slow a dangerous target and create a safer window to move.",
                        "capability": "recon",
                        "power_source": "mundane",
                        "purpose": "control",
                        "dimensions": ["position", "environment"],
                        "rank": 1,
                        "max_rank": 3,
                        "resource_cost": {"mana": 12},
                        "cooldown_turns": 2,
                        "effect_ops": [{"op": "apply_scene_status", "status": "frosted_ground"}],
                    }
                ]
            },
            "ability_state": {"ranks": {"recon_frost_arrow": 2}},
        },
    }


class _Gateway:
    def __init__(self) -> None:
        self.context: dict[str, Any] = {}

    def generate(self, prompt: str, *, context: dict[str, Any], timeout_s: float) -> str:
        assert "exactly two sentences" in prompt
        assert "do not invent additional damage" in prompt
        assert timeout_s == 20.0
        self.context = context
        return (
            "The archer draws a rim of pale rime along the arrowhead before releasing it through the tavern's smoky air. "
            "On impact, the cold steals momentum from the quarry and opens safer ground for the next careful move."
        )


def test_ability_detail_generates_grounded_prose_without_mutating_state(monkeypatch) -> None:
    session = _session()
    before = deepcopy(session)
    gateway = _Gateway()
    monkeypatch.setattr(service, "load_session", lambda session_id: session)
    monkeypatch.setattr(ability_detail, "build_app_llm_gateway", lambda: gateway)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "ability_detail", "session_id": "rpg_test", "ability_name": "Frost Arrow"}
    )

    assert result["ok"] is True
    assert result["ability_detail"]["name"] == "Frost Arrow"
    assert result["ability_detail"]["rank"] == 2
    assert result["ability_detail"]["resource_cost"] == {"mana": 12}
    assert result["ability_detail"]["cooldown_turns"] == 2
    assert result["ability_detail"]["source"] == "llm"
    assert gateway.context["ability"]["effect_ops"] == [
        {"op": "apply_scene_status", "status": "frosted_ground"}
    ]
    assert session == before


def test_ability_detail_uses_deterministic_description_when_llm_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(ability_detail, "build_app_llm_gateway", lambda: None)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "ability_detail", "session_id": "rpg_test", "ability_name": "Frost Arrow"}
    )

    assert result["ok"] is False
    assert result["error"] == "ability_detail_llm_unavailable"
    assert result["ability_detail"]["summary"] == "Slow a dangerous target and create a safer window to move."


def test_ability_detail_requires_session_and_ability_names() -> None:
    assert rpg_session_compat.get_rpg_session_payload({"action": "ability_detail"}) == {
        "ok": False,
        "error": "missing_session_id",
    }
