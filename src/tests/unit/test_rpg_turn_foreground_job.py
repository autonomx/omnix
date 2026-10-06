"""Regression coverage for feature-owned foreground RPG job handling."""

from types import SimpleNamespace

from app.jobs.handlers import registry_from_features
from app.apps.rpg.jobs import turn_executor
from app.runtime.feature_catalog import load_feature


def test_rpg_turn_jobs_are_registered_by_the_rpg_feature() -> None:
    registry = registry_from_features((load_feature("rpg"),))

    turn = registry.require("rpg.turn")
    report = registry.require("rpg.report.last10")

    assert turn.input_model.__name__ == "RpgTurnJobInput"
    assert report.input_model.__name__ == "RpgReportJobInput"
    assert registry.types() == ("rpg.report.last10", "rpg.turn")


def test_foreground_rpg_turn_visible_text_has_deterministic_fallback() -> None:
    result = {"player_input": "I ask Bran how business is going"}

    visible = turn_executor._rpg_turn_visible_text(result)

    assert visible
    assert "Bran" in visible
    assert "Steady enough" in visible


def test_authoritative_social_turn_does_not_call_provider(monkeypatch) -> None:
    command = "I ask Bran how business is going"
    authoritative = {
        "ok": True,
        "player_input": command,
        "final_narration": "Bran explains that the tavern is doing well.",
    }

    monkeypatch.setattr(
        turn_executor,
        "_apply_authoritative_rpg_turn",
        lambda session_id, player_command: authoritative,
    )

    def unexpected_provider_call(*args, **kwargs):
        raise AssertionError("authoritative RPG turns must not call the provider")

    monkeypatch.setattr(turn_executor, "_call_chat_provider", unexpected_provider_call)
    job = SimpleNamespace(
        id="job:rpg-turn",
        type="rpg.turn",
        input_payload={"command": command},
        input_ref={"session_id": "session:1"},
        module="rpg",
    )

    result = turn_executor._render_job(job, job_store=object())

    assert result["content"] == authoritative["final_narration"]
