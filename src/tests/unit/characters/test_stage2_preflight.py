from __future__ import annotations

from pathlib import Path
from typing import Any

from app.characters.stage2_contracts import Stage2Checkpoint, Stage2PrepareConfig
from app.characters.stage2_runner import prepare_stage2, verify_stage2_restart


class FakeStage2Gateway:
    def __init__(self) -> None:
        self.characters: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.memories: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.segment_counter = 0
        self.snapshot_counter = 0
        self.memory_counter = 0
        self.deleted_sessions: list[str] = []
        self.inject_cross_owner_prompt = False
        self.inject_candidate_write = False

    def health(self) -> dict[str, Any]:
        return {"ok": True, "status": "ready"}

    def list_characters(self) -> list[dict[str, Any]]:
        return list(self.characters.values())

    def create_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        value = {
            **payload,
            "active_version": 1,
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        self.characters[str(payload["id"])] = value
        return dict(value)

    def _segment(self) -> str:
        self.segment_counter += 1
        return f"segment:{self.segment_counter}"

    def _identity_hash(self, character_id: str | None) -> str:
        seed = (character_id or "system").encode().hex()
        return (seed + "0" * 64)[:64]

    def _owner(self, session: dict[str, Any]) -> tuple[str, str]:
        if session["interaction_mode"] == "character":
            return "character", str(session["character_id"])
        return "system", "system-assistant"

    def _visible_memories(self, session: dict[str, Any]) -> list[dict[str, Any]]:
        owner = self._owner(session)
        return sorted(
            (
                record
                for record in self.memories.values()
                if (record["owner_type"], record["owner_id"]) == owner
                and record["status"] == "active"
            ),
            key=lambda item: item["id"],
        )

    def _attach_snapshot(self, session: dict[str, Any], *, refresh: bool = False) -> None:
        if session["interaction_mode"] != "character" or not session["read_memory"]:
            session.update(
                memory_snapshot_id=None,
                memory_snapshot_revision=None,
                memory_record_count=0,
                memory_last_refreshed_at=None,
            )
            return
        previous_revision = int(session.get("memory_snapshot_revision") or 0)
        self.snapshot_counter += 1
        snapshot_id = f"memory-snapshot:{self.snapshot_counter}"
        records = self._visible_memories(session)
        items = [
            {
                "memory_record_id": record["id"],
                "record_revision": record["revision"],
                "content": record["content"],
                "active": True,
                "invalidation_reason": None,
            }
            for record in records
        ]
        snapshot = {
            "snapshot_id": snapshot_id,
            "session_id": session["id"],
            "revision": previous_revision + 1 if refresh else 1,
            "token_estimate": 10 * len(items),
            "created_at": "2026-01-01T00:00:00Z",
            "refreshed_at": "2026-01-01T00:00:00Z" if refresh else None,
            "items": items,
            "active_count": len(items),
            "invalidated_count": 0,
        }
        self.snapshots[snapshot_id] = snapshot
        session.update(
            memory_snapshot_id=snapshot_id,
            memory_snapshot_revision=snapshot["revision"],
            memory_record_count=len(items),
            memory_last_refreshed_at="2026-01-01T00:00:00Z",
        )

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = f"chat:{len(self.sessions) + 1}"
        character_id = payload.get("character_id") if payload.get("interaction_mode") == "character" else None
        session = {
            "id": session_id,
            "title": payload.get("title") or "Stage 2",
            "interaction_mode": payload.get("interaction_mode", "system"),
            "character_id": character_id,
            "provider_id": payload.get("provider_id"),
            "model_id": payload.get("model_id"),
            "read_memory": bool(payload.get("read_memory", False)),
            "write_memory": bool(payload.get("write_memory", False)),
            "shared_memory_access": payload.get("shared_memory_access", "none"),
            "transcript_policy": payload.get("transcript_policy", "persistent"),
            "active_segment_id": self._segment(),
            "effective_identity_hash": self._identity_hash(character_id),
            "character_profile_version": 1 if character_id else None,
            "messages": [],
        }
        self._attach_snapshot(session)
        self.sessions[session_id] = session
        return dict(session)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return dict(self.sessions[session_id])

    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions[session_id]
        character_id = payload.get("character_id") if payload.get("interaction_mode") == "character" else None
        session.update(
            interaction_mode=payload["interaction_mode"],
            character_id=character_id,
            read_memory=bool(payload.get("read_memory", False)),
            write_memory=bool(payload.get("write_memory", False)),
            shared_memory_access=payload.get("shared_memory_access", "none"),
            active_segment_id=self._segment(),
            effective_identity_hash=self._identity_hash(character_id),
            character_profile_version=1 if character_id else None,
        )
        self._attach_snapshot(session)
        return dict(session)

    def delete_session(self, session_id: str) -> dict[str, Any]:
        self.sessions.pop(session_id, None)
        self.deleted_sessions.append(session_id)
        return {"ok": True, "session_id": session_id}

    def list_memory(self, session_id: str) -> dict[str, Any]:
        records = [dict(item) for item in self._visible_memories(self.sessions[session_id])]
        return {"records": records, "total": len(records), "session_id": session_id}

    def list_candidates(self, session_id: str) -> dict[str, Any]:
        owner = self._owner(self.sessions[session_id])
        candidates = [
            dict(value)
            for value in self.candidates.values()
            if (value["owner_type"], value["owner_id"]) == owner
        ]
        return {"candidates": candidates, "total": len(candidates), "session_id": session_id}

    def create_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions[str(payload["session_id"])]
        if session["interaction_mode"] == "character" and not session["write_memory"]:
            raise RuntimeError("character_memory_write_disabled")
        self.memory_counter += 1
        owner_type, owner_id = self._owner(session)
        record = {
            "id": f"memory:{self.memory_counter}",
            "owner_type": owner_type,
            "owner_id": owner_id,
            "scope": payload["scope"],
            "scope_id": "global",
            "category": payload["category"],
            "source": "user_saved",
            "content": payload["content"],
            "normalized_content": payload["content"].casefold(),
            "confidence": 1.0,
            "pinned": bool(payload.get("pinned", False)),
            "trust_level": "user_approved",
            "sensitivity": "normal",
            "provenance_type": "user_message",
            "provenance_id": payload["session_id"],
            "status": "active",
            "revision": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "expires_at": None,
        }
        self.memories[record["id"]] = record
        return dict(record)

    def create_memory_status(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        session = self.sessions[str(payload["session_id"])]
        if session["interaction_mode"] == "character" and not session["write_memory"]:
            return 403, {
                "detail": {
                    "code": "memory_policy_rejected",
                    "message": "character_memory_write_disabled",
                }
            }
        return 200, self.create_memory(payload)

    def delete_memory(self, memory_id: str, session_id: str, revision: int) -> dict[str, Any]:
        record = self.memories[memory_id]
        session = self.sessions[session_id]
        if self._owner(session) != (record["owner_type"], record["owner_id"]):
            raise RuntimeError("owner_mismatch")
        if record["revision"] != revision:
            raise RuntimeError("revision_conflict")
        record["status"] = "forgotten"
        for snapshot in self.snapshots.values():
            for item in snapshot["items"]:
                if item["memory_record_id"] == memory_id and item["active"]:
                    item["active"] = False
                    item["content"] = ""
                    item["invalidation_reason"] = "record_forgotten"
            snapshot["active_count"] = sum(1 for item in snapshot["items"] if item["active"])
            snapshot["invalidated_count"] = len(snapshot["items"]) - snapshot["active_count"]
        return {"ok": True, "memory_id": memory_id}

    def memory_state(self, session_id: str) -> dict[str, Any]:
        session = self.sessions[session_id]
        snapshot = self.snapshots.get(str(session.get("memory_snapshot_id")))
        owner_type, owner_id = self._owner(session)
        return {
            "session_id": session_id,
            "memory_enabled": bool(session["read_memory"]),
            "read_memory": session["read_memory"],
            "write_memory": session["write_memory"],
            "owner_type": owner_type,
            "owner_id": owner_id,
            "snapshot_id": session.get("memory_snapshot_id"),
            "snapshot_revision": session.get("memory_snapshot_revision"),
            "memory_record_count": snapshot["active_count"] if snapshot else 0,
            "last_refreshed_at": session.get("memory_last_refreshed_at"),
            "snapshot": dict(snapshot) if snapshot else None,
        }

    def refresh_memory(self, session_id: str, revision: int | None, token_budget: int) -> dict[str, Any]:
        session = self.sessions[session_id]
        if revision != session.get("memory_snapshot_revision"):
            raise RuntimeError("snapshot_revision_conflict")
        self._attach_snapshot(session, refresh=True)
        return self.memory_state(session_id)

    def stream_chat_diagnostics(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> tuple[float, int, dict[str, Any]]:
        session = self.sessions[session_id]
        content = str(payload["content"])
        if content.casefold().startswith("remember that "):
            return 1.0, 50, {
                "generation_status": "completed",
                "memory_command": {
                    "handled": True,
                    "content": "Character memory write is disabled for this Chat.",
                    "command": "save",
                    "mutated": False,
                    "memory_ids": [],
                },
            }
        if self.inject_candidate_write:
            owner_type, owner_id = self._owner(session)
            self.candidates["candidate:injected"] = {
                "id": "candidate:injected",
                "owner_type": owner_type,
                "owner_id": owner_id,
            }
        metadata: dict[str, Any] = {"generation_status": "completed"}
        if session["read_memory"] and session.get("memory_snapshot_id"):
            snapshot = self.snapshots[session["memory_snapshot_id"]]
            selected = [
                item["memory_record_id"] for item in snapshot["items"] if item["active"]
            ]
            if self.inject_cross_owner_prompt:
                foreign = next(
                    (
                        item["id"]
                        for item in self.memories.values()
                        if item["owner_id"] != session["character_id"]
                    ),
                    None,
                )
                if foreign:
                    selected.append(foreign)
            metadata["memory_context"] = {
                "memory_enabled": True,
                "owner_type": "character",
                "owner_id": session["character_id"],
                "snapshot_id": session["memory_snapshot_id"],
                "snapshot_revision": session["memory_snapshot_revision"],
                "selected_memory_ids": selected,
                "selected_memory_count": len(selected),
                "invalidated_count": snapshot["invalidated_count"],
                "excluded_reason_counts": {},
                "status": "resolved",
                "budget": {},
            }
        return 12.5, 42, metadata


def _config() -> Stage2PrepareConfig:
    return Stage2PrepareConfig(
        base_url="http://test",
        provider_id="lmstudio",
        model_id="test-model",
        settle_seconds=0,
    )


def test_prepare_requires_restart_then_final_verification_passes_and_cleans_up(
    tmp_path: Path,
) -> None:
    gateway = FakeStage2Gateway()
    checkpoint_path = tmp_path / "checkpoint.json"

    prepared = prepare_stage2(gateway, _config(), checkpoint_path=checkpoint_path)

    assert prepared.decision == "needs_review"
    assert prepared.metrics.first_token_ms == 12.5
    assert prepared.metrics.selected_memory_count >= 1
    checkpoint = Stage2Checkpoint.model_validate_json(
        checkpoint_path.read_text(encoding="utf-8")
    )
    assert checkpoint.maya_memory_id != checkpoint.alex_memory_id
    assert checkpoint.maya_snapshot_id

    verified = verify_stage2_restart(
        gateway,
        checkpoint,
        settle_seconds=0,
    )

    assert verified.decision == "pass"
    assert verified.metrics.restart_first_token_ms == 12.5
    assert next(
        check for check in verified.checks if check.id == "cleanup.forget_isolation"
    ).status == "pass"
    assert gateway.memories[checkpoint.maya_memory_id]["status"] == "forgotten"
    assert gateway.memories[checkpoint.alex_memory_id]["status"] == "forgotten"
    assert gateway.memories[checkpoint.system_memory_id]["status"] == "forgotten"
    assert len(gateway.deleted_sessions) == 4


def test_cross_owner_prompt_selection_blocks_prepare(tmp_path: Path) -> None:
    gateway = FakeStage2Gateway()
    gateway.inject_cross_owner_prompt = True

    report = prepare_stage2(
        gateway,
        _config(),
        checkpoint_path=tmp_path / "cross-owner.json",
    )

    assert report.decision == "blocked"
    check = next(
        item for item in report.checks if item.id == "prompt.read_only_selection"
    )
    assert check.status == "fail"
    assert "cross-owner" in check.summary


def test_candidate_creation_blocks_read_only_prepare(tmp_path: Path) -> None:
    gateway = FakeStage2Gateway()
    gateway.inject_candidate_write = True

    report = prepare_stage2(
        gateway,
        _config(),
        checkpoint_path=tmp_path / "candidate.json",
    )

    assert report.decision == "blocked"
    check = next(
        item for item in report.checks if item.id == "writes.read_only_guards"
    )
    assert check.status == "fail"
    assert "pending suggestions" in check.summary
