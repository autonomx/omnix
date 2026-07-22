from __future__ import annotations

import threading

from app.rpg.session.genesis.world_forge_contract import (
    CampaignTopicGraph,
    CampaignTopicNode,
)
from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    generate_campaign_topics,
)
from app.rpg.worlds import generation_worker


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
