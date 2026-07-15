from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.session import turn_presenter
from app.rpg.session.turn_presenter import (
    TurnPresentationInvariantError,
    present_authoritative_turn,
)


ROOT = Path(__file__).resolve().parents[4]


def _canonical(response_id: str = "response:phase30") -> dict:
    return {
        "response_id": response_id,
        "blocks": [{"block_id": "block:phase30"}],
    }


def test_entry_point_adopts_one_existing_canonical_response(monkeypatch) -> None:
    calls = 0

    def canonicalize(result, *, session_id, player_input):
        nonlocal calls
        calls += 1
        return result

    monkeypatch.setattr(
        turn_presenter,
        "canonicalize_resolved_turn_result",
        canonicalize,
    )
    result = present_authoritative_turn(
        {"ok": True, "canonical_narrative_response": _canonical()},
        session_id="campaign:phase30",
        player_input="Look around.",
    )
    assert calls == 1
    assert result["turn_presentation_request_count"] == 1
    assert result["turn_presentation_response_id"] == "response:phase30"
    assert result["turn_presentation_entry_point"] == "present_authoritative_turn_v1"


def test_entry_point_rejects_missing_or_changed_response_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        turn_presenter,
        "canonicalize_resolved_turn_result",
        lambda result, **kwargs: {"ok": True},
    )
    with pytest.raises(TurnPresentationInvariantError):
        present_authoritative_turn(
            {"ok": True},
            session_id="campaign:phase30",
            player_input="Look around.",
        )

    monkeypatch.setattr(
        turn_presenter,
        "canonicalize_resolved_turn_result",
        lambda result, **kwargs: {
            **result,
            "canonical_narrative_response": _canonical("response:changed"),
        },
    )
    with pytest.raises(TurnPresentationInvariantError):
        present_authoritative_turn(
            {"ok": True, "canonical_narrative_response": _canonical("response:original")},
            session_id="campaign:phase30",
            player_input="Look around.",
        )


def test_gateway_has_one_narrative_generation_entry_point() -> None:
    gateway = (
        ROOT / "src" / "app" / "gateway" / "rpg_turn_pipeline.py"
    ).read_text(encoding="utf-8")
    assert gateway.count("present_authoritative_turn(") == 1
    assert "canonicalize_scene_turn_result" not in gateway
    assert "canonicalize_resolved_turn_result" not in gateway
    assert 'rpg_pipeline_span("turn.narrative_present")' in gateway
    assert 'rpg_pipeline_span("turn.narrative_scene_cutover")' not in gateway
    assert 'rpg_pipeline_span("turn.narrative_resolved_cutover")' not in gateway
    assert 'payload["turn_presentation_request_count"]' in gateway
