from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.characters.stage1_preflight import (
    Stage1Checkpoint,
    Stage1PrepareConfig,
    prepare_stage1,
    verify_stage1_restart,
)


class FakeStage1Gateway:
    def __init__(self) -> None:
        self.characters: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.memory_total = 0
        self.candidate_total = 0
        self.segment_counter = 0
        self.voice: dict[str, Any] = {
            "asset_id": "voice-cloning:maya",
            "subject_owner": "Maya voice subject",
            "source_type": "test_recording",
            "source_reference": "test:consent",
            "creator_id": "user:local",
            "consent_status": "granted",
            "consent_recorded_at": "2026-01-01T00:00:00Z",
            "allowed_uses": ["character", "live_call"],
            "source_sha256": "a" * 64,
            "deletion_state": "active",
            "deletion_requested_at": None,
            "deleted_at": None,
            "deletion_reason": "",
            "updated_at": "2026-01-01T00:00:00Z",
        }

    def health(self) -> dict[str, Any]:
        return {"ok": True, "status": "ready"}

    def list_characters(self) -> list[dict[str, Any]]:
        return list(self.characters.values())

    def create_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        character = {
            **payload,
            "active_version": 1,
            "status": "active",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        self.characters[str(payload["id"])] = character
        return character

    def update_character(self, character_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.characters[character_id]
        character = {
            **current,
            **{key: value for key, value in payload.items() if key not in {"expected_version", "clear_default_voice"}},
            "active_version": int(current["active_version"]) + 1,
        }
        if payload.get("clear_default_voice"):
            character["default_voice_asset_id"] = None
        self.characters[character_id] = character
        return character

    def get_character(self, character_id: str) -> dict[str, Any]:
        return self.characters[character_id]

    def voice_governance(self, asset_id: str) -> dict[str, Any]:
        assert asset_id == self.voice["asset_id"]
        return dict(self.voice)

    def update_voice_governance(self, asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.voice = {
            **self.voice,
            **payload,
            "asset_id": asset_id,
            "source_sha256": "b" * 64,
            "consent_recorded_at": "2026-01-02T00:00:00Z",
        }
        return dict(self.voice)

    def _segment(self) -> str:
        self.segment_counter += 1
        return f"segment:{self.segment_counter}"

    @staticmethod
    def _identity_hash(character_id: str) -> str:
        return (character_id.encode("utf-8").hex() + "0" * 64)[:64]

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session_id = f"chat:{len(self.sessions) + 1}"
        character_id = payload.get("character_id") if payload.get("interaction_mode") == "character" else None
        character = self.characters.get(str(character_id)) if character_id else None
        session = {
            "id": session_id,
            "title": payload.get("title") or "Stage 1",
            "interaction_mode": payload.get("interaction_mode", "system"),
            "character_id": character_id,
            "voice_asset_id": payload.get("voice_asset_id") or (character or {}).get("default_voice_asset_id"),
            "read_memory": bool(payload.get("read_memory", False)),
            "write_memory": bool(payload.get("write_memory", False)),
            "shared_memory_access": payload.get("shared_memory_access", "none"),
            "transcript_policy": payload.get("transcript_policy", "persistent"),
            "active_segment_id": self._segment(),
            "character_profile_version": (character or {}).get("active_version"),
            "effective_identity_hash": self._identity_hash(str(character_id)) if character_id else "f" * 64,
            "memory_snapshot_id": None,
            "memory_record_count": 0,
            "messages": [],
        }
        self.sessions[session_id] = session
        return dict(session)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return dict(self.sessions[session_id])

    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions[session_id]
        character_id = payload.get("character_id") if payload.get("interaction_mode") == "character" else None
        character = self.characters.get(str(character_id)) if character_id else None
        session.update(
            {
                "interaction_mode": payload["interaction_mode"],
                "character_id": character_id,
                "voice_asset_id": payload.get("voice_asset_id") or (character or {}).get("default_voice_asset_id"),
                "read_memory": bool(payload.get("read_memory", False)),
                "write_memory": bool(payload.get("write_memory", False)),
                "shared_memory_access": payload.get("shared_memory_access", "none"),
                "active_segment_id": self._segment(),
                "character_profile_version": (character or {}).get("active_version"),
                "effective_identity_hash": self._identity_hash(str(character_id)) if character_id else "f" * 64,
                "memory_snapshot_id": None,
                "memory_record_count": 0,
            }
        )
        return dict(session)

    def live_call_runtime(self, session_id: str) -> dict[str, Any]:
        session = self.sessions[session_id]
        character = self.characters.get(str(session.get("character_id")))
        return {
            "session_id": session_id,
            "interaction_mode": session["interaction_mode"],
            "display_name": character["display_name"] if character else "System Assistant",
            "character_id": session.get("character_id"),
            "character_profile_version": session.get("character_profile_version"),
            "effective_identity_hash": session.get("effective_identity_hash"),
            "voice_asset_id": session.get("voice_asset_id"),
            "greeting": character["default_greeting"] if character else "",
            "speech_style": (character or {}).get(
                "speech_style",
                {
                    "speed": 1.0,
                    "temperature": 0.6,
                    "top_k": 20,
                    "top_p": 0.85,
                    "repetition_penalty": 1.0,
                },
            ),
            "read_memory": session["read_memory"],
            "write_memory": session["write_memory"],
            "shared_memory_access": session["shared_memory_access"],
            "memory_snapshot_id": None,
            "preload": {
                "profile_loaded": character is not None,
                "voice_resolved": bool(session.get("voice_asset_id")),
                "memory_snapshot_loaded": False,
                "memory_record_count": 0,
                "preload_ms": 1.25,
                "resolved_at": "2026-01-01T00:00:00Z",
            },
        }

    def list_memory(self, session_id: str) -> dict[str, Any]:
        return {"records": [], "total": self.memory_total, "session_id": session_id}

    def list_candidates(self, session_id: str) -> dict[str, Any]:
        return {"candidates": [], "total": self.candidate_total, "session_id": session_id}

    def stream_chat(self, session_id: str, payload: dict[str, Any]) -> tuple[float, str]:
        self.sessions[session_id]["messages"].extend(
            [
                {"role": "user", "content": payload["content"]},
                {"role": "assistant", "content": "Stage 1 is ready."},
            ]
        )
        return 42.5, "Stage 1 is ready."

    def stream_tts(self, payload: dict[str, Any]) -> tuple[float, int]:
        return 73.25, 4096


def _config(**updates: Any) -> Stage1PrepareConfig:
    return Stage1PrepareConfig(
        base_url="http://test",
        character_id="stage1-maya",
        display_name="Maya Stage 1",
        greeting="Hey, good to hear from you.",
        settle_seconds=0,
        **updates,
    )


def test_prepare_generates_needs_review_checkpoint_then_restart_passes(tmp_path: Path) -> None:
    gateway = FakeStage1Gateway()
    checkpoint_path = tmp_path / "checkpoint.json"

    prepared = prepare_stage1(gateway, _config(), checkpoint_path=checkpoint_path)

    assert prepared.decision == "needs_review"
    assert prepared.metrics.first_token_ms == 42.5
    assert prepared.metrics.first_audio_chunk_ms == 73.25
    assert prepared.metrics.first_audio_chunk_bytes == 4096
    assert checkpoint_path.is_file()
    checkpoint = Stage1Checkpoint.model_validate_json(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint.character_id == "stage1-maya"
    assert checkpoint.character_profile_version == 1
    assert len(checkpoint.effective_identity_hash) == 64
    assert next(check for check in prepared.checks if check.id == "memory.no_activity").status == "pass"

    verified = verify_stage1_restart(gateway, checkpoint)

    assert verified.decision == "pass"
    assert next(check for check in verified.checks if check.id == "restart.persistence").status == "pass"


def test_voice_governance_must_be_explicit_before_character_link(tmp_path: Path) -> None:
    gateway = FakeStage1Gateway()
    gateway.voice.update(
        {
            "consent_status": "unverified",
            "allowed_uses": [],
            "subject_owner": "",
            "creator_id": "",
        }
    )

    blocked = prepare_stage1(
        gateway,
        _config(voice_asset_id="voice-cloning:maya"),
        checkpoint_path=tmp_path / "blocked.json",
    )

    assert blocked.decision == "blocked"
    governance = next(check for check in blocked.checks if check.id == "voice.governance")
    assert governance.status == "fail"
    assert "not governed" in governance.summary

    prepared = prepare_stage1(
        gateway,
        _config(
            voice_asset_id="voice-cloning:maya",
            apply_voice_governance=True,
            confirm_voice_consent=True,
            voice_subject_owner="Maya voice subject",
            voice_source_type="user_recording",
            voice_source_reference="consent-session:one",
            voice_creator_id="user:local",
        ),
        checkpoint_path=tmp_path / "governed.json",
    )
    assert prepared.decision == "needs_review"
    assert gateway.voice["consent_status"] == "granted"
    assert set(gateway.voice["allowed_uses"]) == {"character", "live_call"}


def test_memory_delta_blocks_stage1(tmp_path: Path) -> None:
    gateway = FakeStage1Gateway()

    def stream_chat_with_candidate(session_id: str, payload: dict[str, Any]):
        gateway.candidate_total += 1
        return 20.0, "Unexpected memory candidate."

    gateway.stream_chat = stream_chat_with_candidate  # type: ignore[method-assign]
    report = prepare_stage1(
        gateway,
        _config(skip_tts=True),
        checkpoint_path=tmp_path / "memory-delta.json",
    )

    assert report.decision == "blocked"
    memory_check = next(check for check in report.checks if check.id == "memory.no_activity")
    assert memory_check.status == "fail"
    assert "memory changed" in memory_check.summary


def test_skipped_provider_and_tts_require_review_but_preserve_identity_checks(tmp_path: Path) -> None:
    gateway = FakeStage1Gateway()
    report = prepare_stage1(
        gateway,
        _config(skip_generation=True, skip_tts=True),
        checkpoint_path=tmp_path / "manual.json",
    )

    assert report.decision == "needs_review"
    assert next(check for check in report.checks if check.id == "identity.voice_only_is_system").status == "pass"
    assert next(check for check in report.checks if check.id == "identity.segment_switching").status == "pass"
    assert next(check for check in report.checks if check.id == "latency.first_token").status == "review"
    assert next(check for check in report.checks if check.id == "latency.first_audio_chunk").status == "review"
    payload = json.loads((tmp_path / "manual.json").read_text(encoding="utf-8"))
    assert payload["format_version"] == "character-stage1-v1"
