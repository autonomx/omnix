from __future__ import annotations

from dataclasses import dataclass

from app.rpg.narrative_engine import (
    BeatKind,
    BeatPurpose,
    CanonicalNarrativeResponse,
    DeliveryMetadata,
    DeliveryMode,
    GenerationMetadata,
    NarrativeBlock,
    NarrativeEngineService,
    ValidationReport,
)
from app.rpg.narrative_repository import (
    PostgresNarrativeResponseRepositoryAdapter,
    build_production_narrative_repository,
    reset_narrative_repository_cache,
)


@dataclass(frozen=True)
class _Context:
    workspace_id: str = "workspace:phase31"


class _Store:
    def __init__(self) -> None:
        self.by_id = {}
        self.by_turn = {}

    def save(self, context, response):
        frozen = response.with_content_hash()
        key = (frozen.campaign_id, frozen.turn_id)
        existing = self.by_turn.get(key)
        if existing is not None:
            return existing
        self.by_id[frozen.response_id] = frozen
        self.by_turn[key] = frozen
        return frozen

    def get(self, context, response_id):
        return self.by_id.get(response_id)

    def get_for_turn(self, context, campaign_id, turn_id):
        return self.by_turn.get((campaign_id, turn_id))

    def list_campaign(self, context, campaign_id, limit=500):
        return tuple(
            value for value in self.by_id.values()
            if value.campaign_id == campaign_id
        )[:limit]


class _Work:
    def __init__(self, store):
        self.narrative_responses = store
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _UowFactory:
    def __init__(self, store):
        self.store = store
        self.works = []

    def __call__(self, database):
        work = _Work(self.store)
        self.works.append(work)
        return work


def _response() -> CanonicalNarrativeResponse:
    return CanonicalNarrativeResponse(
        response_id="response:phase31",
        request_id="request:phase31",
        turn_id="turn:phase31",
        campaign_id="campaign:phase31",
        revision=1,
        blocks=(
            NarrativeBlock(
                block_id="block:phase31",
                beat_id="beat:phase31",
                sequence=1,
                kind=BeatKind.NARRATION,
                purpose=BeatPurpose.RESOLVED_ACTION,
                text="The lantern catches against the wet stones.",
            ),
        ),
        evidence_used=(),
        validation=ValidationReport(passed=True),
        generation=GenerationMetadata(source="fixture"),
        delivery=DeliveryMetadata(mode=DeliveryMode.BLOCKING),
    ).with_content_hash()


def test_postgres_adapter_commits_save_and_reads_exact_response() -> None:
    store = _Store()
    uow = _UowFactory(store)
    contexts = 0

    def context_provider(database):
        nonlocal contexts
        contexts += 1
        return _Context()

    adapter = PostgresNarrativeResponseRepositoryAdapter(
        object(),
        context_provider=context_provider,
        unit_of_work_factory=uow,
    )
    response = _response()
    saved = adapter.save(response)
    replayed = adapter.save(response)
    loaded = adapter.get(response.response_id)
    by_turn = adapter.get_for_turn(response.campaign_id, response.turn_id)
    listed = adapter.list_campaign(response.campaign_id)

    assert saved == replayed == loaded == by_turn == response
    assert listed == (response,)
    assert contexts == 1
    assert uow.works[0].committed is True
    assert all(work.rolled_back for work in uow.works[2:])


def test_production_mode_selects_postgresql_and_portable_mode_is_shared_memory() -> None:
    reset_narrative_repository_cache()
    try:
        postgres = build_production_narrative_repository(
            environ={"OMNIX_RPG_NARRATIVE_REPOSITORY": "postgresql"}
        )
        first = build_production_narrative_repository(
            environ={"OMNIX_RPG_NARRATIVE_REPOSITORY": "in_memory"}
        )
        second = build_production_narrative_repository(
            environ={"OMNIX_RPG_NARRATIVE_REPOSITORY": "in_memory"}
        )
        assert isinstance(postgres, PostgresNarrativeResponseRepositoryAdapter)
        assert first is second
    finally:
        reset_narrative_repository_cache()


def test_engine_default_resolves_external_production_repository(monkeypatch) -> None:
    from app.rpg.narrative_engine import EvidenceBroker

    store = _Store()
    repository = PostgresNarrativeResponseRepositoryAdapter(
        object(),
        context_provider=lambda database: _Context(),
        unit_of_work_factory=_UowFactory(store),
    )
    monkeypatch.setattr(
        "app.rpg.narrative_repository.build_production_narrative_repository",
        lambda: repository,
    )
    service = NarrativeEngineService(evidence_broker=EvidenceBroker([]))
    assert service.repository is repository
