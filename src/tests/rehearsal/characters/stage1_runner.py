"""Pure orchestration for the Character Mode Stage 1 deployment rehearsal."""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .stage1_contracts import (
    Stage1Check,
    Stage1Checkpoint,
    Stage1Metrics,
    Stage1PrepareConfig,
    Stage1Report,
    duration_ms,
    report_decision,
    safe_error,
    utcnow,
)
from .stage1_http import Stage1Gateway


def _count(payload: dict[str, Any], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, list):
        return len(value)
    return 0


def _check(
    checks: list[Stage1Check],
    check_id: str,
    operation: Callable[[], tuple[Any, str, dict[str, Any]]],
) -> Any:
    started = time.perf_counter()
    try:
        value, summary, observed = operation()
    except Exception as exc:
        checks.append(
            Stage1Check(
                id=check_id,
                status="fail",
                summary=safe_error(exc),
                duration_ms=duration_ms(started),
            )
        )
        return None
    checks.append(
        Stage1Check(
            id=check_id,
            status="pass",
            summary=summary,
            duration_ms=duration_ms(started),
            observed=observed,
        )
    )
    return value


def _health(gateway: Stage1Gateway):
    payload = gateway.health()
    if payload.get("ok") is not True or payload.get("status") != "ready":
        raise RuntimeError("Gateway health endpoint is not ready")
    return payload, "Gateway health endpoint is ready.", {"ready": True}


def _ensure_character(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
) -> dict[str, Any]:
    existing = next(
        (item for item in gateway.list_characters() if item.get("id") == config.character_id),
        None,
    )
    expected = {
        "display_name": config.display_name,
        "personality_prompt": config.personality_prompt,
        "default_greeting": config.greeting,
        "default_voice_asset_id": config.voice_asset_id,
        "speech_style": {
            "speed": 1.0,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.0,
            "expressiveness": "warm",
            "default_emotion": "calm",
            "interruption_style": "balanced",
        },
        "identity_policy": {
            "may_claim_to_be_human": False,
            "may_claim_real_world_experiences": False,
            "disclosure_required": True,
        },
        "shared_memory_policy": {"access": "none", "allowed_categories": []},
        "enabled": True,
    }
    if existing is None:
        return gateway.create_character({"id": config.character_id, **expected})
    if existing.get("status") == "archived":
        raise RuntimeError("the requested Stage 1 character is archived")
    mismatches = [key for key, value in expected.items() if existing.get(key) != value]
    if not mismatches:
        return existing
    if not config.update_existing_character:
        raise RuntimeError(
            "existing Stage 1 character differs from requested profile: "
            + ", ".join(sorted(mismatches))
        )
    return gateway.update_character(
        config.character_id,
        {
            "expected_version": existing.get("active_version"),
            **expected,
            "clear_default_voice": config.voice_asset_id is None,
        },
    )


def _ensure_voice_governance(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
) -> dict[str, Any] | None:
    if not config.voice_asset_id:
        return None
    governance = gateway.voice_governance(config.voice_asset_id)
    ready = (
        governance.get("consent_status") == "granted"
        and governance.get("deletion_state") == "active"
        and {"character", "live_call"}.issubset(
            set(governance.get("allowed_uses") or [])
        )
        and bool(governance.get("subject_owner"))
        and bool(governance.get("creator_id"))
        and bool(governance.get("source_sha256"))
    )
    if ready:
        return governance
    if not config.apply_voice_governance:
        raise RuntimeError(
            "linked voice is not governed for both character and live_call use"
        )
    if not config.confirm_voice_consent:
        raise RuntimeError("--confirm-voice-consent is required before granting consent")
    required = {
        "voice_subject_owner": config.voice_subject_owner,
        "voice_source_type": config.voice_source_type,
        "voice_creator_id": config.voice_creator_id,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise RuntimeError("voice governance fields are missing: " + ", ".join(missing))
    return gateway.update_voice_governance(
        config.voice_asset_id,
        {
            "subject_owner": config.voice_subject_owner.strip(),
            "source_type": config.voice_source_type.strip(),
            "source_reference": config.voice_source_reference.strip(),
            "creator_id": config.voice_creator_id.strip(),
            "consent_status": "granted",
            "allowed_uses": ["character", "live_call"],
            "deletion_state": "active",
            "deletion_reason": "",
        },
    )


def _create_and_validate_system_session(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
):
    session = gateway.create_session(
        {
            "title": "Stage 1 voice-only System Assistant check",
            "provider_id": config.provider_id,
            "model_id": config.model_id,
            "voice_asset_id": config.voice_asset_id,
            "interaction_mode": "system",
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
        }
    )
    runtime = gateway.live_call_runtime(str(session["id"]))
    if session.get("interaction_mode") != "system" or session.get("character_id") is not None:
        raise RuntimeError("voice-only session activated a character")
    if runtime.get("interaction_mode") != "system" or runtime.get("character_id") is not None:
        raise RuntimeError("voice-only live-call runtime activated a character")
    if runtime.get("display_name") != "System Assistant":
        raise RuntimeError("voice-only runtime did not resolve the System Assistant")
    return (
        session,
        "Selecting a renderer voice alone remains System Assistant mode.",
        {
            "session_id": session.get("id"),
            "interaction_mode": session.get("interaction_mode"),
            "voice_asset_id": runtime.get("voice_asset_id"),
        },
    )


def _create_and_validate_character_session(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
    character: dict[str, Any],
):
    session = gateway.create_session(
        {
            "title": "Stage 1 Character identity check",
            "provider_id": config.provider_id,
            "model_id": config.model_id,
            "interaction_mode": "character",
            "character_id": config.character_id,
            "voice_asset_id": config.voice_asset_id,
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
        }
    )
    expected_version = int(character.get("active_version") or 0)
    if session.get("interaction_mode") != "character":
        raise RuntimeError("character session did not enter Character Mode")
    if session.get("character_id") != config.character_id:
        raise RuntimeError("character session resolved the wrong owner")
    if session.get("read_memory") or session.get("write_memory"):
        raise RuntimeError("Stage 1 character session enabled memory")
    if session.get("shared_memory_access") != "none":
        raise RuntimeError("Stage 1 character session enabled shared memory")
    if session.get("memory_snapshot_id") is not None or int(
        session.get("memory_record_count") or 0
    ):
        raise RuntimeError("Stage 1 character session created a memory snapshot")
    if int(session.get("character_profile_version") or 0) != expected_version:
        raise RuntimeError("session profile version does not match the active character version")
    identity_hash = str(session.get("effective_identity_hash") or "")
    if len(identity_hash) != 64:
        raise RuntimeError("session did not persist an effective identity hash")
    return (
        session,
        "Character identity is server-resolved with memory fully disabled.",
        {
            "session_id": session.get("id"),
            "profile_version": session.get("character_profile_version"),
            "identity_hash": identity_hash,
            "segment_id": session.get("active_segment_id"),
        },
    )


def _memory_baseline(gateway: Stage1Gateway, session_id: str):
    records = gateway.list_memory(session_id)
    candidates = gateway.list_candidates(session_id)
    baseline = {
        "records": _count(records, "total") or _count(records, "records"),
        "candidates": _count(candidates, "total") or _count(candidates, "candidates"),
    }
    return (
        baseline,
        "Captured the character owner's pre-rehearsal memory baseline.",
        baseline,
    )


def _validate_runtime(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
    character: dict[str, Any],
    session: dict[str, Any],
):
    runtime = gateway.live_call_runtime(str(session["id"]))
    if runtime.get("interaction_mode") != "character":
        raise RuntimeError("live-call runtime did not resolve Character Mode")
    if runtime.get("character_id") != config.character_id:
        raise RuntimeError("live-call runtime resolved the wrong character")
    if runtime.get("display_name") != character.get("display_name"):
        raise RuntimeError("text and live-call character names do not match")
    if runtime.get("character_profile_version") != session.get("character_profile_version"):
        raise RuntimeError("text and live-call profile versions do not match")
    if runtime.get("effective_identity_hash") != session.get("effective_identity_hash"):
        raise RuntimeError("text and live-call identity hashes do not match")
    if runtime.get("greeting") != character.get("default_greeting"):
        raise RuntimeError("live-call greeting does not match the character profile")
    if runtime.get("voice_asset_id") != config.voice_asset_id:
        raise RuntimeError("live-call renderer voice does not match the requested voice")
    preload = runtime.get("preload") if isinstance(runtime.get("preload"), dict) else {}
    if preload.get("memory_snapshot_loaded") or int(preload.get("memory_record_count") or 0):
        raise RuntimeError("live-call runtime preloaded character memory during Stage 1")
    return (
        runtime,
        "Text and live-call paths share the same profile version and identity hash.",
        {
            "profile_version": runtime.get("character_profile_version"),
            "identity_hash": runtime.get("effective_identity_hash"),
            "voice_asset_id": runtime.get("voice_asset_id"),
            "preload_ms": preload.get("preload_ms"),
            "memory_snapshot_loaded": preload.get("memory_snapshot_loaded"),
        },
    )


def _switch_identity(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
    initial_session: dict[str, Any],
    initial_runtime: dict[str, Any],
):
    session_id = str(initial_session["id"])
    initial_segment = initial_session.get("active_segment_id")
    system = gateway.set_interaction(
        session_id,
        {
            "interaction_mode": "system",
            "character_id": None,
            "voice_asset_id": config.voice_asset_id,
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
            "continue_topic": False,
        },
    )
    if system.get("interaction_mode") != "system" or system.get("character_id") is not None:
        raise RuntimeError("switch to System Assistant failed")
    system_segment = system.get("active_segment_id")
    if not system_segment or system_segment == initial_segment:
        raise RuntimeError("identity switch did not create a new System Assistant segment")
    character = gateway.set_interaction(
        session_id,
        {
            "interaction_mode": "character",
            "character_id": config.character_id,
            "voice_asset_id": config.voice_asset_id,
            "read_memory": False,
            "write_memory": False,
            "shared_memory_access": "none",
            "transcript_policy": "persistent",
            "continue_topic": False,
        },
    )
    character_segment = character.get("active_segment_id")
    if not character_segment or character_segment in {initial_segment, system_segment}:
        raise RuntimeError("switch back to Character Mode did not create a clean segment")
    if character.get("effective_identity_hash") != initial_runtime.get("effective_identity_hash"):
        raise RuntimeError("returning to the same character changed the effective identity")
    runtime = gateway.live_call_runtime(session_id)
    if runtime.get("effective_identity_hash") != character.get("effective_identity_hash"):
        raise RuntimeError("post-switch live-call identity does not match the text session")
    return (
        (character, runtime),
        "System Assistant and Character Mode switches create clean persisted segments.",
        {
            "initial_segment_id": initial_segment,
            "system_segment_id": system_segment,
            "character_segment_id": character_segment,
            "identity_hash": character.get("effective_identity_hash"),
        },
    )


def _run_generation(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
    session_id: str,
):
    first_token_ms, response_text = gateway.stream_chat(
        session_id,
        {
            "content": config.probe_text,
            "provider_id": config.provider_id,
            "model_id": config.model_id,
        },
    )
    if not response_text:
        raise RuntimeError("provider returned an empty Stage 1 response")
    return (
        (first_token_ms, response_text),
        "Character text generation produced a streamed first token.",
        {
            "first_token_ms": first_token_ms,
            "response_character_count": len(response_text),
        },
    )


def _run_tts(
    gateway: Stage1Gateway,
    runtime: dict[str, Any],
    text: str,
):
    style = runtime.get("speech_style") if isinstance(runtime.get("speech_style"), dict) else {}
    first_audio_ms, chunk_bytes = gateway.stream_tts(
        {
            "text": text[:1000],
            "speaker": runtime.get("voice_asset_id"),
            "language": "English",
            "chunk_size": 8,
            "temperature": style.get("temperature", 0.6),
            "top_k": style.get("top_k", 20),
            "top_p": style.get("top_p", 0.85),
            "repetition_penalty": style.get("repetition_penalty", 1.0),
            "append_silence": False,
            "max_new_tokens": 180,
            "non_streaming_mode": False,
            "parity_mode": True,
            "request_id": f"character-stage1:{uuid.uuid4().hex}",
        }
    )
    if chunk_bytes <= 0:
        raise RuntimeError("TTS returned an empty first audio chunk")
    return (
        (first_audio_ms, chunk_bytes),
        "Streaming TTS produced the first audio chunk for the resolved Character runtime.",
        {"first_audio_chunk_ms": first_audio_ms, "first_audio_chunk_bytes": chunk_bytes},
    )


def _validate_memory_unchanged(
    gateway: Stage1Gateway,
    session_id: str,
    baseline: dict[str, int],
):
    records = gateway.list_memory(session_id)
    candidates = gateway.list_candidates(session_id)
    after = {
        "records": _count(records, "total") or _count(records, "records"),
        "candidates": _count(candidates, "total") or _count(candidates, "candidates"),
    }
    session = gateway.get_session(session_id)
    if after != baseline:
        raise RuntimeError(
            f"character memory changed during Stage 1: before={baseline}, after={after}"
        )
    if session.get("memory_snapshot_id") is not None or int(
        session.get("memory_record_count") or 0
    ):
        raise RuntimeError("Stage 1 session gained a character memory snapshot")
    if session.get("read_memory") or session.get("write_memory"):
        raise RuntimeError("Stage 1 session memory permissions changed")
    return (
        after,
        "No character memory records, candidates, or snapshots were added or read.",
        {"before": baseline, "after": after, "snapshot_id": None},
    )


def _prepare_report(
    config: Stage1PrepareConfig,
    checks: list[Stage1Check],
    metrics: Stage1Metrics,
    checkpoint_path: str | Path,
    session_id: str | None,
) -> Stage1Report:
    return Stage1Report(
        generated_at=utcnow(),
        mode="prepare",
        decision=report_decision(checks),
        base_url=config.base_url,
        character_id=config.character_id,
        character_session_id=session_id,
        checks=checks,
        metrics=metrics,
        checkpoint_path=str(checkpoint_path),
        notes=[
            "Reports contain IDs, counts, hashes, and timings only; prompt, transcript, memory, and audio content are not persisted.",
            "A final pass requires post-restart verification.",
        ],
    )


def prepare_stage1(
    gateway: Stage1Gateway,
    config: Stage1PrepareConfig,
    *,
    checkpoint_path: str | Path,
) -> Stage1Report:
    checks: list[Stage1Check] = []
    metrics = Stage1Metrics()

    if _check(checks, "gateway.health", lambda: _health(gateway)) is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, None)

    if config.voice_asset_id:
        governance = _check(
            checks,
            "voice.governance",
            lambda: (
                _ensure_voice_governance(gateway, config),
                "Linked voice has ownership, consent, provenance, hash, and required uses.",
                {
                    "voice_asset_id": config.voice_asset_id,
                    "uses": ["character", "live_call"],
                },
            ),
        )
        if governance is None:
            return _prepare_report(config, checks, metrics, checkpoint_path, None)
    else:
        checks.append(
            Stage1Check(
                id="voice.governance",
                status="pass",
                summary="No cloned voice requested; the deployment renderer will be used.",
                observed={"voice_asset_id": None},
            )
        )

    character = _check(
        checks,
        "character.profile",
        lambda: (
            _ensure_character(gateway, config),
            "Versioned Stage 1 character profile is active.",
            {"character_id": config.character_id},
        ),
    )
    if character is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, None)

    system_session = _check(
        checks,
        "identity.voice_only_is_system",
        lambda: _create_and_validate_system_session(gateway, config),
    )
    if system_session is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, None)

    character_session = _check(
        checks,
        "identity.character_session",
        lambda: _create_and_validate_character_session(gateway, config, character),
    )
    if character_session is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, None)

    session_id = str(character_session["id"])
    baseline_memory = _check(
        checks,
        "memory.baseline",
        lambda: _memory_baseline(gateway, session_id),
    )
    if baseline_memory is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, session_id)

    runtime = _check(
        checks,
        "live_call.runtime",
        lambda: _validate_runtime(gateway, config, character, character_session),
    )
    if runtime is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, session_id)
    metrics.runtime_preload_ms = float(runtime.get("preload", {}).get("preload_ms") or 0)

    switched = _check(
        checks,
        "identity.segment_switching",
        lambda: _switch_identity(gateway, config, character_session, runtime),
    )
    if switched is None:
        return _prepare_report(config, checks, metrics, checkpoint_path, session_id)
    final_session, final_runtime = switched

    response_text = config.greeting
    if config.skip_generation:
        checks.append(
            Stage1Check(
                id="latency.first_token",
                status="review",
                summary="LLM generation was skipped; first-token latency requires a live provider rehearsal.",
            )
        )
    else:
        generation = _check(
            checks,
            "latency.first_token",
            lambda: _run_generation(gateway, config, session_id),
        )
        if generation is not None:
            first_token_ms, response_text = generation
            metrics.first_token_ms = first_token_ms
            metrics.response_character_count = len(response_text)

    if config.skip_tts:
        checks.append(
            Stage1Check(
                id="latency.first_audio_chunk",
                status="review",
                summary="Streaming TTS was skipped; first-audio latency requires the live TTS service.",
            )
        )
    else:
        tts = _check(
            checks,
            "latency.first_audio_chunk",
            lambda: _run_tts(gateway, final_runtime, response_text or config.greeting),
        )
        if tts is not None:
            metrics.first_audio_chunk_ms, metrics.first_audio_chunk_bytes = tts

    if config.settle_seconds:
        time.sleep(config.settle_seconds)
    _check(
        checks,
        "memory.no_activity",
        lambda: _validate_memory_unchanged(gateway, session_id, baseline_memory),
    )

    checks.append(
        Stage1Check(
            id="restart.persistence",
            status="review",
            summary=(
                "Restart the Omnix services, then run verify-restart with the generated checkpoint."
            ),
            observed={"checkpoint_required": True},
        )
    )

    if any(check.status == "fail" for check in checks):
        return _prepare_report(config, checks, metrics, checkpoint_path, session_id)

    checkpoint = Stage1Checkpoint(
        created_at=utcnow(),
        base_url=config.base_url,
        character_id=config.character_id,
        character_display_name=str(character.get("display_name") or config.display_name),
        character_profile_version=int(final_session.get("character_profile_version") or 0),
        character_session_id=session_id,
        character_segment_id=str(final_session.get("active_segment_id") or ""),
        effective_identity_hash=str(final_session.get("effective_identity_hash") or ""),
        voice_asset_id=config.voice_asset_id,
        prepare_checks=checks,
        prepare_metrics=metrics,
    )
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(checkpoint.model_dump_json(indent=2), encoding="utf-8")
    return _prepare_report(config, checks, metrics, path, session_id)


def verify_stage1_restart(
    gateway: Stage1Gateway,
    checkpoint: Stage1Checkpoint,
) -> Stage1Report:
    checks = [
        check.model_copy()
        for check in checkpoint.prepare_checks
        if check.id != "restart.persistence"
    ]
    started = time.perf_counter()
    try:
        character = gateway.get_character(checkpoint.character_id)
        session = gateway.get_session(checkpoint.character_session_id)
        runtime = gateway.live_call_runtime(checkpoint.character_session_id)
        if int(character.get("active_version") or 0) != checkpoint.character_profile_version:
            raise RuntimeError("character profile version changed across restart")
        if session.get("active_segment_id") != checkpoint.character_segment_id:
            raise RuntimeError("active character segment changed across restart")
        if session.get("effective_identity_hash") != checkpoint.effective_identity_hash:
            raise RuntimeError("session identity hash changed across restart")
        if runtime.get("effective_identity_hash") != checkpoint.effective_identity_hash:
            raise RuntimeError("live-call identity hash changed across restart")
        if runtime.get("character_profile_version") != checkpoint.character_profile_version:
            raise RuntimeError("live-call profile version changed across restart")
        if runtime.get("voice_asset_id") != checkpoint.voice_asset_id:
            raise RuntimeError("live-call renderer voice changed across restart")
        if session.get("memory_snapshot_id") is not None or int(
            session.get("memory_record_count") or 0
        ):
            raise RuntimeError("memory snapshot appeared after restart")
        checks.append(
            Stage1Check(
                id="restart.persistence",
                status="pass",
                summary="Character profile, segment, identity hash, voice, and memory-off state survived restart.",
                duration_ms=duration_ms(started),
                observed={
                    "profile_version": checkpoint.character_profile_version,
                    "segment_id": checkpoint.character_segment_id,
                    "identity_hash": checkpoint.effective_identity_hash,
                    "voice_asset_id": checkpoint.voice_asset_id,
                },
            )
        )
    except Exception as exc:
        checks.append(
            Stage1Check(
                id="restart.persistence",
                status="fail",
                summary=safe_error(exc),
                duration_ms=duration_ms(started),
            )
        )
    return Stage1Report(
        generated_at=utcnow(),
        mode="verify-restart",
        decision=report_decision(checks),
        base_url=checkpoint.base_url,
        character_id=checkpoint.character_id,
        character_session_id=checkpoint.character_session_id,
        checks=checks,
        metrics=checkpoint.prepare_metrics,
        notes=[
            "Post-restart verification re-read the profile, session, and live-call runtime through HTTP APIs.",
            "No prompt, transcript, memory, or audio content was persisted in this report.",
        ],
    )


__all__ = ["prepare_stage1", "verify_stage1_restart"]
