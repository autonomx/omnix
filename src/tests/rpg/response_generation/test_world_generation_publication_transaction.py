from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.rpg.worlds import generation_certified_publication as certified
from app.rpg.worlds.generation_publication_transaction import (
    WorldGenerationCertificationError,
    publication_transaction_report,
    require_certified_publication,
)


def _run(*, progress: dict | None = None) -> dict:
    return {
        "run_id": "run:1",
        "world_id": "world:1",
        "status": "review",
        "draft_revision": 1,
        "progress": dict(progress or {}),
        "plan": {},
    }


def _certification(*, launch_ready: bool = True) -> dict:
    return {
        "launch_ready": launch_ready,
        "missing_requirements": [] if launch_ready else ["consistency_audit"],
        "consistency_report": {"passed": launch_ready},
        "strict_integrity": {"passed": launch_ready},
        "profile_reference_integrity": {"passed": launch_ready},
        "profile_dossier_policy": {"passed": launch_ready},
    }


def test_transaction_rejects_stale_topics_even_when_certification_passes() -> None:
    report = publication_transaction_report(
        _run(
            progress={
                "publication_blocked": True,
                "potentially_stale_topic_ids": ["actors", "opening_threads"],
            }
        ),
        _certification(),
    )

    assert report["publishable"] is False
    assert report["reasons"] == [
        "progress_publication_blocked",
        "unresolved_topic_blockers",
    ]
    assert report["topic_blockers"]["potentially_stale_topic_ids"] == [
        "actors",
        "opening_threads",
    ]


def test_transaction_rejects_any_failed_certification_report() -> None:
    with pytest.raises(WorldGenerationCertificationError) as exc_info:
        require_certified_publication(_run(), _certification(launch_ready=False))

    report = exc_info.value.report
    assert report["publishable"] is False
    assert report["launch_ready"] is False
    assert report["missing_requirements"] == ["consistency_audit"]
    assert set(report["failed_reports"]) == {
        "consistency_report",
        "strict_integrity",
        "profile_reference_integrity",
        "profile_dossier_policy",
    }


def test_transaction_accepts_reviewed_launch_ready_snapshot() -> None:
    report = publication_transaction_report(_run(), _certification())

    assert report["publishable"] is True
    assert report["reasons"] == []
    assert report["failed_reports"] == {}


class _GenerationRepository:
    def get(self, _context: object, _run_id: str) -> dict:
        return _run()

    def list_topics(
        self,
        _context: object,
        *,
        world_id: str,
        draft_revision: int,
    ) -> list[dict]:
        del world_id, draft_revision
        return []

    def update(self, *_args: object, **_kwargs: object) -> dict:
        raise AssertionError("run must not be updated for failed certification")


class _WorldScenarios:
    def publish_world_revision(self, *_args: object, **_kwargs: object) -> dict:
        raise AssertionError("revision must not be persisted for failed certification")

    def publish_world_release(self, *_args: object, **_kwargs: object) -> dict:
        raise AssertionError("release must not be persisted for failed certification")


class _Cursor:
    def fetchone(self) -> tuple[int]:
        return (0,)


class _Connection:
    def execute(self, *_args: object, **_kwargs: object) -> _Cursor:
        return _Cursor()


class _Work:
    def __init__(self) -> None:
        self.world_generation = _GenerationRepository()
        self.world_scenarios = _WorldScenarios()
        self.connection = _Connection()

    def __enter__(self) -> "_Work":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def rollback(self) -> None:
        return None

    def commit(self) -> None:
        raise AssertionError("failed certification must not commit")


def test_failed_certification_performs_no_durable_publication_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work = _Work()
    monkeypatch.setattr(
        certified,
        "bootstrap_local_tenant",
        lambda _database: SimpleNamespace(workspace_id="workspace:1"),
    )
    monkeypatch.setattr(certified, "unit_of_work", lambda _database: work)
    monkeypatch.setattr(
        certified,
        "require_world_writable",
        lambda *_args: {"id": "world:1", "title": "World"},
    )
    monkeypatch.setattr(certified, "approved_world_asset_bindings", lambda *_args: {})
    monkeypatch.setattr(
        certified,
        "compile_world_generation_certified_artifact",
        lambda **_kwargs: SimpleNamespace(
            publication=None,
            certification=_certification(launch_ready=False),
        ),
    )

    with pytest.raises(WorldGenerationCertificationError):
        certified.publish_certified_world_generation("run:1", database=object())
