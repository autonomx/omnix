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


def test_world_forge_content_generation_is_single_pass() -> None:
    assert ReferenceSafeWorldForgeGenerator._max_regeneration_attempts({}) == 1
    assert (
        ReferenceSafeWorldForgeGenerator._max_regeneration_attempts(
            {"targeted_regeneration_max_attempts": 5}
        )
        == 1
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
        seed=17,
    )
    context = {"world_brief": {"title": "Concurrent Realm"}}
    fingerprint, input_hash, directive_hash = topic_generation_fingerprint(
        graph.node_map()["realm"],
        normalized_topic_input={
            "generation_context": context,
            "target_count": 1,
            "visibility": "game_master_canon",
            "dependency_trust": {},
        },
        dependency_hashes={},
        directives={},
        entity_manifest_hash="sha256:manifest",
        settings=settings,
    )
    rows = {
        "realm": {
            "topic_id": "realm",
            "status": "ready",
            "source": "ai",
            "content_hash": "sha256:realm",
            "input_hash": input_hash,
            "dependency_hashes": {},
            "provenance": {
                "run_id": "run:current",
                "generation_fingerprint": fingerprint,
                "directive_hash": directive_hash,
            },
        }
    }

    available, reusable, protected = available_completed_topics(
        graph,
        rows=rows,
        generation_context=context,
        topic_directives={},
        entity_manifest_hash="sha256:manifest",
        settings=settings,
        forced_topic_ids=("realm",),
        current_run_id="run:current",
    )

    assert set(available) == {"realm"}
    assert reusable == ("realm",)
    assert protected == ()


def test_worker_database_recovery_does_not_refund_attempts(monkeypatch) -> None:
    class _Connection:
        def __init__(self) -> None:
            self.query = ""

        def execute(self, query: str, params: object):
            del params
            self.query = query
            return type("_Result", (), {"rowcount": 1})()

    class _Work:
        def __init__(self) -> None:
            self.connection = _Connection()
            self.committed = False

        def commit(self) -> None:
            self.committed = True

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            del args

    work = _Work()
    monkeypatch.setattr(
        "app.persistence.identity_service.bootstrap_local_tenant",
        lambda database: type("_Context", (), {"workspace_id": "workspace:local"})(),
    )
    monkeypatch.setattr(
        "app.persistence.unit_of_work.unit_of_work",
        lambda database: work,
    )

    recovered = generation_worker._recover_worker_database_interruption(
        "worker:1",
        database=object(),
    )

    assert recovered == 1
    assert "attempt_count = GREATEST" not in work.connection.query
    assert "attempt_count < max_attempts" in work.connection.query
    assert work.committed is True


def test_worker_surfaces_database_unavailability(monkeypatch) -> None:
    monkeypatch.setattr(
        generation_worker,
        "run_world_generation_worker_once",
        lambda **kwargs: (_ for _ in ()).throw(DatabaseUnavailableError("offline")),
    )
    state = generation_worker._WorkerPoolState()
    state.stop = True
    generation_worker._worker_loop(1, object(), state)
