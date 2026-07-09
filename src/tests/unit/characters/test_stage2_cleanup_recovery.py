from __future__ import annotations

from typing import Any

from app.characters.stage2_contracts import (
    Stage2Check,
    Stage2Checkpoint,
    Stage2Metrics,
    Stage2Report,
)
from app.characters.stage2_verification import (
    cleanup_and_verify_forget,
    resume_stage2_cleanup,
)


class PurgingCleanupGateway:
    def __init__(self, checkpoint: Stage2Checkpoint, *, maya_already_deleted: bool) -> None:
        self.checkpoint = checkpoint
        self.records: dict[str, dict[str, dict[str, Any]]] = {
            checkpoint.maya_setup_session_id: {},
            checkpoint.alex_setup_session_id: {
                checkpoint.alex_memory_id: {
                    "id": checkpoint.alex_memory_id,
                    "revision": 1,
                }
            },
            checkpoint.system_setup_session_id: {
                checkpoint.system_memory_id: {
                    "id": checkpoint.system_memory_id,
                    "revision": 1,
                }
            },
        }
        if not maya_already_deleted:
            self.records[checkpoint.maya_setup_session_id][checkpoint.maya_memory_id] = {
                "id": checkpoint.maya_memory_id,
                "revision": 1,
            }
        self.snapshot_revision = checkpoint.maya_snapshot_revision
        self.snapshot_items = (
            []
            if maya_already_deleted
            else [
                {
                    "memory_record_id": checkpoint.maya_memory_id,
                    "record_revision": 1,
                    "content": "synthetic",
                    "active": True,
                    "invalidation_reason": None,
                }
            ]
        )
        self.interaction_updates: list[str] = []
        self.deleted_sessions: list[str] = []

    def list_memory(self, session_id: str) -> dict[str, Any]:
        records = list(self.records[session_id].values())
        return {"records": records, "total": len(records), "session_id": session_id}

    def delete_memory(
        self,
        memory_id: str,
        session_id: str,
        revision: int,
    ) -> dict[str, Any]:
        record = self.records[session_id].get(memory_id)
        if record is None:
            raise AssertionError(f"unexpected missing memory: {memory_id}")
        assert revision == record["revision"]
        del self.records[session_id][memory_id]
        self.snapshot_items = [
            item
            for item in self.snapshot_items
            if item["memory_record_id"] != memory_id
        ]
        return {"ok": True, "memory_id": memory_id}

    def memory_state(self, session_id: str) -> dict[str, Any]:
        assert session_id == self.checkpoint.maya_pilot_session_id
        return {
            "session_id": session_id,
            "memory_enabled": True,
            "read_memory": True,
            "write_memory": False,
            "owner_type": "character",
            "owner_id": self.checkpoint.maya_character_id,
            "snapshot_id": self.checkpoint.maya_snapshot_id,
            "snapshot_revision": self.snapshot_revision,
            "memory_record_count": len(self.snapshot_items),
            "last_refreshed_at": "2026-07-09T00:00:00Z",
            "snapshot": {
                "snapshot_id": self.checkpoint.maya_snapshot_id,
                "session_id": session_id,
                "revision": self.snapshot_revision,
                "token_estimate": 0,
                "created_at": "2026-07-09T00:00:00Z",
                "refreshed_at": None,
                "items": list(self.snapshot_items),
                "active_count": len(self.snapshot_items),
                "invalidated_count": 0,
            },
        }

    def refresh_memory(
        self,
        session_id: str,
        revision: int | None,
        token_budget: int,
    ) -> dict[str, Any]:
        assert session_id == self.checkpoint.maya_pilot_session_id
        assert revision == self.snapshot_revision
        assert token_budget == 4_000
        self.snapshot_revision += 1
        self.snapshot_items = []
        return self.memory_state(session_id)

    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["write_memory"] is False
        self.interaction_updates.append(session_id)
        return {"id": session_id, **payload}

    def delete_session(self, session_id: str) -> dict[str, Any]:
        self.deleted_sessions.append(session_id)
        return {"ok": True, "session_id": session_id}


def _checkpoint() -> Stage2Checkpoint:
    return Stage2Checkpoint(
        created_at="2026-07-09T00:00:00Z",
        base_url="http://127.0.0.1:8000",
        provider_id="lmstudio",
        model_id="test-model",
        run_id="stage2-readonly-v1",
        maya_character_id="stage2-maya",
        alex_character_id="stage2-alex",
        maya_setup_session_id="chat:maya-setup",
        alex_setup_session_id="chat:alex-setup",
        system_setup_session_id="chat:system-setup",
        maya_pilot_session_id="chat:maya-pilot",
        alex_pilot_session_id="chat:alex-pilot",
        maya_segment_id="segment:maya",
        maya_identity_hash="a" * 64,
        maya_snapshot_id="memory-snapshot:maya",
        maya_snapshot_revision=2,
        maya_memory_id="memory:maya",
        alex_memory_id="memory:alex",
        system_memory_id="memory:system",
        baseline_maya_record_ids=["memory:maya"],
        baseline_maya_candidate_ids=[],
        marker_hashes={"maya": "m", "alex": "a", "system": "s"},
        prepare_checks=[],
        prepare_metrics=Stage2Metrics(
            first_token_ms=2500,
            restart_first_token_ms=None,
            selected_memory_count=1,
            snapshot_record_count=1,
            context_switch_count=2,
        ),
    )


def _failed_report(checkpoint: Stage2Checkpoint) -> Stage2Report:
    return Stage2Report(
        generated_at="2026-07-09T00:05:00Z",
        mode="verify-restart",
        decision="blocked",
        base_url=checkpoint.base_url,
        run_id=checkpoint.run_id,
        maya_character_id=checkpoint.maya_character_id,
        maya_pilot_session_id=checkpoint.maya_pilot_session_id,
        checks=[
            Stage2Check(
                id="restart.persistence",
                status="pass",
                summary="restart passed",
            ),
            Stage2Check(
                id="restart.prompt_selection",
                status="pass",
                summary="prompt passed",
            ),
            Stage2Check(
                id="restart.read_only_guards",
                status="pass",
                summary="guards passed",
            ),
            Stage2Check(
                id="cleanup.forget_isolation",
                status="fail",
                summary="forget did not invalidate the active Maya snapshot item",
            ),
        ],
        metrics=checkpoint.prepare_metrics.model_copy(
            update={"restart_first_token_ms": 2200}
        ),
    )


def test_cleanup_accepts_server_snapshot_item_purge() -> None:
    checkpoint = _checkpoint()
    gateway = PurgingCleanupGateway(checkpoint, maya_already_deleted=False)

    _, _, observed = cleanup_and_verify_forget(gateway, checkpoint, 4_000)

    assert observed["maya_deleted_during_this_run"] is True
    assert observed["maya_projection_mode"] == "purged_item"
    assert observed["maya_active_after_forget"] is False
    assert gateway.records[checkpoint.alex_setup_session_id] == {}
    assert gateway.records[checkpoint.system_setup_session_id] == {}
    assert len(gateway.deleted_sessions) == 4


def test_resume_cleanup_finishes_known_partial_failure() -> None:
    checkpoint = _checkpoint()
    gateway = PurgingCleanupGateway(checkpoint, maya_already_deleted=True)

    report = resume_stage2_cleanup(
        gateway,
        checkpoint,
        _failed_report(checkpoint),
        token_budget=4_000,
    )

    assert report.decision == "pass"
    cleanup = next(
        item for item in report.checks if item.id == "cleanup.forget_isolation"
    )
    assert cleanup.status == "pass"
    assert cleanup.observed["maya_deleted_during_this_run"] is False
    assert cleanup.observed["maya_projection_mode"] == "purged_item"
    assert next(
        item for item in report.checks if item.id == "recovery.prior_evidence"
    ).status == "pass"
    assert len(gateway.deleted_sessions) == 4


def test_resume_cleanup_rejects_unrelated_failure() -> None:
    checkpoint = _checkpoint()
    gateway = PurgingCleanupGateway(checkpoint, maya_already_deleted=True)
    failed = _failed_report(checkpoint)
    failed.checks[-1].summary = "different cleanup failure"

    report = resume_stage2_cleanup(gateway, checkpoint, failed)

    assert report.decision == "blocked"
    evidence = next(
        item for item in report.checks if item.id == "recovery.prior_evidence"
    )
    assert evidence.status == "fail"
    assert gateway.deleted_sessions == []
