from __future__ import annotations

from pathlib import Path

from app.rpg.narrative_engine import (
    EvidenceBroker,
    NarrativeBlock,
    NarrativeEngineService,
    TurnPresentationRequest,
    WriterResult,
)
from app.rpg.narrative_engine.persistence_policy import (
    narrative_repository_save_policy,
)


ROOT = Path(__file__).resolve().parents[4]


class _Writer:
    def write(self, request, plan, evidence):
        return WriterResult(
            blocks=tuple(
                NarrativeBlock(
                    block_id=f"block:{beat.sequence}",
                    beat_id=beat.beat_id,
                    sequence=beat.sequence,
                    kind=beat.kind,
                    purpose=beat.purpose,
                    speaker_id=beat.speaker_id,
                    evidence_refs=beat.evidence_refs,
                    claim_refs=beat.required_claim_refs,
                    text="The rain taps against the shutters.",
                )
                for beat in plan.beats
            ),
            source="phase33_writer",
        )


class _Repository:
    def __init__(self) -> None:
        self.saves = 0
        self.lookups = 0

    def save(self, response):
        self.saves += 1
        return response

    def get(self, response_id):
        return None

    def get_for_turn(self, campaign_id, turn_id):
        self.lookups += 1
        return None


def _request() -> TurnPresentationRequest:
    return TurnPresentationRequest(
        request_id="request:phase33",
        turn_id="turn:phase33",
        campaign_id="campaign:phase33",
        player_input="Listen to the rain.",
        authoritative_outcome={
            "response_mode": "observation",
            "allowed_claim_refs": [],
        },
        metadata={"response_mode": "observation"},
    )


def test_outer_transaction_policy_stages_canon_without_repository_side_effect() -> None:
    repository = _Repository()
    service = NarrativeEngineService(
        evidence_broker=EvidenceBroker([]),
        writer=_Writer(),
        repository=repository,
    )

    with narrative_repository_save_policy(defer=True):
        generated = service.generate(_request())

    assert generated.response.validation.passed is True
    assert generated.response.content_hash
    assert repository.lookups == 0
    assert repository.saves == 0


def test_production_hook_generates_canon_before_postgresql_commit() -> None:
    hook = (
        ROOT / "src" / "app" / "rpg" / "session" / "interaction_timeline_hook.py"
    ).read_text(encoding="utf-8")
    service = (
        ROOT / "src" / "app" / "persistence" / "rpg_turn_service.py"
    ).read_text(encoding="utf-8")

    assert hook.index("canonicalize_resolved_turn_result(") < hook.index(
        "persist_foreground_turn("
    )
    assert "narrative_repository_save_policy(defer=postgres_active)" in hook
    assert service.index("work.narrative_responses.save(") < service.index(
        "work.rpg.commit_turn("
    )
    assert '"narrative_atomic_with_turn": stored_narrative is not None' in service
