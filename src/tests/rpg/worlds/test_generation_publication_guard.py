from __future__ import annotations

import pytest

from app.rpg.worlds import generation_publication_guard as guard


class _GenerationRepository:
    def __init__(self, results: list[dict], topics: list[dict]) -> None:
        self.results = results
        self.topics = topics

    def get(self, context, run_id: str) -> dict:
        del context
        return {
            "run_id": run_id,
            "world_id": "world:1",
            "draft_revision": 1,
            "context": {"target_topic_ids": ["setting_rules", "actors"]},
        }

    def list_topic_results(self, context, *, run_id: str) -> list[dict]:
        del context, run_id
        return list(self.results)

    def list_topics(self, context, *, world_id: str, draft_revision: int) -> list[dict]:
        del context, world_id, draft_revision
        return list(self.topics)


class _Work:
    def __init__(self, results: list[dict], topics: list[dict]) -> None:
        self.world_generation = _GenerationRepository(results, topics)

    def rollback(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        del args


def _install(monkeypatch: pytest.MonkeyPatch, results: list[dict], topics: list[dict]) -> None:
    monkeypatch.setattr(guard, "bootstrap_local_tenant", lambda database: object())
    monkeypatch.setattr(guard, "unit_of_work", lambda database: _Work(results, topics))


def test_publication_report_rejects_flagged_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        [
            {
                "topic_id": "setting_rules",
                "status": "accepted",
                "candidate_hash": "sha256:rules",
                "validation": {"reason_codes": []},
            },
            {
                "topic_id": "actors",
                "status": "needs_review",
                "candidate_hash": "sha256:actors",
                "validation": {"reason_codes": ["missing_required_structured_field"]},
            },
        ],
        [
            {
                "topic_id": "setting_rules",
                "status": "ready",
                "content_hash": "sha256:rules",
            }
        ],
    )

    report = guard.publication_review_report("run:1")

    assert report["publishable"] is False
    assert report["flagged_topic_ids"] == ["actors"]
    assert report["reason_counts"] == {"missing_required_structured_field": 1}
    with pytest.raises(guard.WorldGenerationRequiresReviewError) as raised:
        guard.publish_world_generation("run:1")
    assert raised.value.report == report


def test_publication_report_requires_promoted_hash_match(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        {
            "topic_id": "setting_rules",
            "status": "accepted",
            "candidate_hash": "sha256:rules",
            "validation": {"reason_codes": []},
        },
        {
            "topic_id": "actors",
            "status": "accepted",
            "candidate_hash": "sha256:actors",
            "validation": {"reason_codes": []},
        },
    ]
    _install(
        monkeypatch,
        results,
        [
            {
                "topic_id": "setting_rules",
                "status": "ready",
                "content_hash": "sha256:rules",
            },
            {
                "topic_id": "actors",
                "status": "ready",
                "content_hash": "sha256:old-actors",
            },
        ],
    )

    mismatch = guard.publication_review_report("run:1")
    assert mismatch["publishable"] is False
    assert mismatch["hash_mismatch_topic_ids"] == ["actors"]

    _install(
        monkeypatch,
        results,
        [
            {
                "topic_id": "setting_rules",
                "status": "ready",
                "content_hash": "sha256:rules",
            },
            {
                "topic_id": "actors",
                "status": "ready",
                "content_hash": "sha256:actors",
            },
        ],
    )
    accepted = guard.publication_review_report("run:1")
    assert accepted["publishable"] is True
    assert accepted["hash_mismatch_topic_ids"] == []
