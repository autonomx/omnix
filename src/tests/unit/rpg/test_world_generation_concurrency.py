from __future__ import annotations

import threading

from app.persistence.database import DatabaseUnavailableError
from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    generate_campaign_topics,
)
from app.rpg.worlds.generation_coordinator import available_completed_topics
from app.rpg.worlds.generation_jobs import (
    WorldTopicGenerationSettings,
    topic_generation_fingerprint,
)
from app.rpg.worlds import generation_worker
from app.rpg.session.genesis.world_forge_default import ReferenceSafeWorldForgeGenerator


class _ConcurrentGenerator:
    def __init__(self, expected_peak: int) -> None:
        self.expected_peak = expected_peak
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()
        self._reached_peak = threading.Event()

    def generate(self, node: CampaignTopicNode, **kwargs: object) -> GeneratedTopic:
        del kwargs
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if self.active == self.expected_peak:
                self._reached_peak.set()
        assert self._reached_peak.wait(timeout=2)
        try:
            return GeneratedTopic(topic_id=node.topic_id)
        finally:
            with self._lock:
                self.active -= 1


def _independent_graph(count: int = 8) -> CampaignTopicGraph:
    return CampaignTopicGraph(
        graph_version="concurrency-test-v1",
        campaign_template="test",
        depth="standard",
        nodes=tuple(
            CampaignTopicNode(
                topic_id=f"topic-{index}",
                title=f"Topic {index}",
                category="lore",
            )
            for index in range(count)
        ),
    )


def test_world_forge_hard_caps_parallel_llm_calls_at_four() -> None:
    generator = _ConcurrentGenerator(expected_peak=4)

    result = generate_campaign_topics(
        _independent_graph(),
        generator=generator,
        max_parallel_jobs=99,
    )

    assert result.passed is True
    assert generator.peak == 4
    assert [topic.topic_id for topic in result.topics] == [
        f"topic-{index}" for index in range(8)
    ]


def test_world_forge_respects_a_lower_parallel_limit() -> None:
    generator = _ConcurrentGenerator(expected_peak=2)

    result = generate_campaign_topics(
        _independent_graph(4),
        generator=generator,
        max_parallel_jobs=2,
    )

    assert result.passed is True
    assert generator.peak == 2


def test_world_forge_limits_targeted_regeneration_to_one_retry() -> None:
    assert ReferenceSafeWorldForgeGenerator._max_regeneration_attempts({}) == 2
    assert (
        ReferenceSafeWorldForgeGenerator._max_regeneration_attempts(
            {"targeted_regeneration_max_attempts": 5}
        )
        == 2
    )


def test_completed_forced_topic_from_current_run_unblocks_dependents() -> None:
    graph = CampaignTopicGraph(
        graph_version="forced-topic-test-v1",
        campaign_template="test",
        depth="quick",
        nodes=(
            CampaignTopicNode(topic_id="realm", title="Realm", category="lore"),
            CampaignTopicNode(
                topic_id="races",
                title="Races",
                category="races",
                dependencies=("realm",),
            ),
        ),
    )
    settings = WorldTopicGenerationSettings(
        generator_version="test-v1",
        prompt_version="test-prompt-v1",
        provider_route="lmstudio",
        model="test-model",
        seed=1,
    )
    context = {"genre": "fantasy"}
    manifest_hash = "sha256:manifest"
    realm = graph.nodes[0]
    races = graph.nodes[1]
    realm_fingerprint, realm_input_hash, realm_directive_hash = topic_generation_fingerprint(
        realm,
        normalized_topic_input={
            "generation_context": context,
            "target_count": realm.target_count,
            "visibility": realm.visibility,
        },
        dependency_hashes={},
        directives={},
        entity_manifest_hash=manifest_hash,
        settings=settings,
    )
    realm_hash = "sha256:realm"
    races_fingerprint, races_input_hash, races_directive_hash = topic_generation_fingerprint(
        races,
        normalized_topic_input={
            "generation_context": context,
            "target_count": races.target_count,
            "visibility": races.visibility,
        },
        dependency_hashes={"realm": realm_hash},
        directives={},
        entity_manifest_hash=manifest_hash,
        settings=settings,
    )
    rows = {
        "realm": {
            "status": "ready",
            "source": "ai",
            "content_hash": realm_hash,
            "input_hash": realm_input_hash,
            "dependency_hashes": {},
            "provenance": {
                "generation_fingerprint": realm_fingerprint,
                "directive_hash": realm_directive_hash,
                "run_id": "run:earlier",
            },
        },
        "races": {
            "status": "ready",
            "source": "ai",
            "content_hash": "sha256:races",
            "input_hash": races_input_hash,
            "dependency_hashes": {"realm": realm_hash},
            "provenance": {
                "generation_fingerprint": races_fingerprint,
                "directive_hash": races_directive_hash,
                "run_id": "run:continuation",
            },
        },
    }

    available, _, _ = available_completed_topics(
        graph,
        rows=rows,
        generation_context=context,
        topic_directives={},
        entity_manifest_hash=manifest_hash,
        settings=settings,
        forced_topic_ids=("races",),
        current_run_id="run:continuation",
    )

    assert set(available) == {"realm", "races"}


def test_durable_world_generation_worker_pool_runs_four_slots(monkeypatch) -> None:
    barrier = threading.Barrier(4, timeout=2)
    calls: dict[str, int] = {}
    lock = threading.Lock()

    def fake_run_once(*, worker_id: str, database: object) -> dict[str, bool] | None:
        del database
        with lock:
            calls[worker_id] = calls.get(worker_id, 0) + 1
            first_call = calls[worker_id] == 1
        if not first_call:
            return None
        barrier.wait()
        return {"ok": True}

    monkeypatch.setattr(
        generation_worker,
        "run_world_generation_worker_once",
        fake_run_once,
    )
    monkeypatch.setattr(
        generation_worker,
        "_recover_interrupted_jobs",
        lambda **_kwargs: {"discarded": 0, "requeued": 0},
    )

    generation_worker._worker_pool_loop(None, "openrouter")

    assert sorted(calls) == [
        "rpg-world-generation:local:1",
        "rpg-world-generation:local:2",
        "rpg-world-generation:local:3",
        "rpg-world-generation:local:4",
    ]
    assert all(count >= 1 for count in calls.values())


def test_worker_waits_for_a_scheduled_retry_before_claiming_again(monkeypatch) -> None:
    results = iter(({"status": "retrying"}, {"status": "completed"}, None))
    sleeps: list[float] = []

    monkeypatch.setattr(
        generation_worker,
        "run_world_generation_worker_once",
        lambda **_kwargs: next(results),
    )
    monkeypatch.setattr(generation_worker.time, "sleep", sleeps.append)

    generation_worker._worker_loop(
        1,
        None,
        generation_worker._WorkerPoolState(),
    )

    assert sleeps == [generation_worker._RETRY_POLL_SECONDS]


def test_worker_pauses_for_database_recovery_without_stopping(monkeypatch) -> None:
    calls = iter((DatabaseUnavailableError("database unavailable"), None))
    sleeps: list[float] = []
    recoveries: list[str] = []

    def run_once(**_kwargs):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(generation_worker, "run_world_generation_worker_once", run_once)
    monkeypatch.setattr(generation_worker, "_recover_worker_database_interruption", lambda worker_id, **_kwargs: recoveries.append(worker_id) or 1)
    monkeypatch.setattr(generation_worker.time, "sleep", sleeps.append)
    monkeypatch.setattr(generation_worker, "log_world_generation_event", lambda *args, **kwargs: {})

    generation_worker._worker_loop(1, None, generation_worker._WorkerPoolState())

    assert recoveries == ["rpg-world-generation:local:1"]
    assert sleeps == [generation_worker._DATABASE_RECOVERY_POLL_SECONDS]
