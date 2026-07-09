from __future__ import annotations

from pathlib import Path
from typing import Any

from app.characters.stage3_contracts import Stage3Checkpoint, Stage3PrepareConfig
from app.characters.stage3_runner import prepare_stage3, verify_stage3_restart

from test_stage2_preflight import FakeStage2Gateway


class FakeStage3Gateway(FakeStage2Gateway):
    def __init__(self) -> None:
        super().__init__()
        self.candidate_counter = 0
        self.create_candidates = True

    def update_memory(
        self,
        memory_id: str,
        session_id: str,
        revision: int,
        content: str,
    ) -> dict[str, Any]:
        record = self.memories[memory_id]
        if record["revision"] != revision:
            raise RuntimeError("revision_conflict")
        record["content"] = content
        record["normalized_content"] = content.casefold()
        record["revision"] += 1
        return dict(record)

    def approve_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        pinned: bool = False,
    ) -> dict[str, Any]:
        candidate = self.candidates[candidate_id]
        session = self.sessions[session_id]
        if self._owner(session) != (candidate["owner_type"], candidate["owner_id"]):
            raise RuntimeError("owner_mismatch")
        if candidate["status"] != "pending":
            raise RuntimeError("candidate_not_pending")
        candidate["status"] = "accepted"
        return self.create_memory(
            {
                "session_id": session_id,
                "scope": candidate["proposed_scope"],
                "category": candidate["proposed_category"],
                "content": candidate["proposed_content"],
                "pinned": pinned,
            }
        )

    def reject_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        pinned: bool = False,
    ) -> dict[str, Any]:
        candidate = self.candidates[candidate_id]
        session = self.sessions[session_id]
        if self._owner(session) != (candidate["owner_type"], candidate["owner_id"]):
            raise RuntimeError("owner_mismatch")
        candidate["status"] = "rejected"
        return dict(candidate)

    def delete_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        expected_status: str,
    ) -> dict[str, Any]:
        candidate = self.candidates[candidate_id]
        session = self.sessions[session_id]
        if self._owner(session) != (candidate["owner_type"], candidate["owner_id"]):
            raise RuntimeError("owner_mismatch")
        if candidate["status"] != expected_status:
            raise RuntimeError("candidate_status_mismatch")
        del self.candidates[candidate_id]
        return {"ok": True, "candidate_id": candidate_id}

    def list_candidates(self, session_id: str) -> dict[str, Any]:
        owner = self._owner(self.sessions[session_id])
        candidates = [
            dict(value)
            for value in self.candidates.values()
            if (value["owner_type"], value["owner_id"]) == owner
            and value.get("status") == "pending"
        ]
        return {"candidates": candidates, "total": len(candidates), "session_id": session_id}

    def list_jobs(self, *, limit: int = 100, full: bool = True) -> list[dict[str, Any]]:
        return [
            {
                "id": "job:memory-suggest",
                "type": "assistant.memory.suggest",
                "status": "completed" if self.create_candidates else "queued",
            }
        ]

    def _create_candidate(self, session_id: str, content: str) -> dict[str, Any]:
        self.candidate_counter += 1
        session = self.sessions[session_id]
        owner_type, owner_id = self._owner(session)
        candidate = {
            "id": f"candidate:{self.candidate_counter}",
            "owner_type": owner_type,
            "owner_id": owner_id,
            "source_session_id": session_id,
            "source_message_id": f"msg:candidate:{self.candidate_counter}",
            "candidate_fingerprint": f"fingerprint:{self.candidate_counter}",
            "proposed_scope": "global",
            "proposed_scope_id": "global",
            "proposed_category": "fact",
            "proposed_content": content,
            "confidence": 0.8,
            "source": "assistant_suggested",
            "trust_level": "unverified_agent",
            "sensitivity": "normal",
            "extraction_metadata": {},
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
            "resolved_at": None,
        }
        self.candidates[candidate["id"]] = candidate
        return candidate

    def stream_chat_diagnostics(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> tuple[float, int, dict[str, Any]]:
        session = self.sessions[session_id]
        content = str(payload["content"])
        if content.casefold().startswith("remember that "):
            if not session["write_memory"]:
                return super().stream_chat_diagnostics(session_id, payload)
            record = self.create_memory(
                {
                    "session_id": session_id,
                    "scope": "global",
                    "category": "fact",
                    "content": content[14:].strip(),
                    "pinned": False,
                }
            )
            return 1.0, 50, {
                "generation_status": "completed",
                "memory_command": {
                    "handled": True,
                    "content": "Saved.",
                    "command": "save",
                    "mutated": True,
                    "memory_ids": [record["id"]],
                },
            }
        if self.create_candidates and (
            content.casefold().startswith("my stage three")
            or content.casefold().startswith("i prefer ")
        ):
            self._create_candidate(session_id, content)
        return super().stream_chat_diagnostics(session_id, payload)


def _config() -> Stage3PrepareConfig:
    return Stage3PrepareConfig(
        base_url="http://test",
        provider_id="lmstudio",
        model_id="test-model",
        settle_seconds=0,
    )


def test_prepare_requires_restart_then_final_verification_passes_and_cleans_up(
    tmp_path: Path,
) -> None:
    gateway = FakeStage3Gateway()
    checkpoint_path = tmp_path / "checkpoint.json"

    prepared = prepare_stage3(gateway, _config(), checkpoint_path=checkpoint_path)

    assert prepared.decision == "needs_review"
    assert prepared.metrics.explicit_record_count == 1
    assert prepared.metrics.pending_candidate_count == 1
    assert prepared.metrics.approved_record_count == 1
    checkpoint = Stage3Checkpoint.model_validate_json(
        checkpoint_path.read_text(encoding="utf-8")
    )
    assert checkpoint.maya_explicit_memory_id
    assert checkpoint.approved_candidate_id
    assert checkpoint.approved_candidate_memory_id

    verified = verify_stage3_restart(gateway, checkpoint)

    assert verified.decision == "pass"
    assert next(
        item for item in verified.checks if item.id == "cleanup.stage3_fixtures"
    ).status == "pass"
    assert len(gateway.deleted_sessions) == 3
    assert gateway.candidates == {}
    assert all(record["status"] == "forgotten" for record in gateway.memories.values())


def test_prepare_blocks_when_suggestion_worker_does_not_materialize_candidate(
    tmp_path: Path,
) -> None:
    gateway = FakeStage3Gateway()
    gateway.create_candidates = False

    report = prepare_stage3(
        gateway,
        _config(),
        checkpoint_path=tmp_path / "blocked.json",
    )

    assert report.decision == "blocked"
    check = next(item for item in report.checks if item.id == "suggestions.pending_approval")
    assert check.status == "fail"
    assert "pending suggestion did not appear" in check.summary
