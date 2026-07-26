"""Runtime artifact verification built on immutable World Forge topic results."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from .generation_authorship import (
    AuthorshipClass,
    AuthorshipValidationError,
    attach_human_authorship,
    attach_llm_authorship,
    content_hash,
    lore_string_leaves,
    prove_structural_repair_non_authoring,
    validate_publishable_authorship as _validate_origins,
)


def _authored_payload_hash(candidate: Mapping[str, Any]) -> str:
    return content_hash(
        [
            {"path": row["path"], "content_hash": row["content_hash"]}
            for row in lore_string_leaves(candidate)
        ]
    )


def _artifact_without_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    artifact = deepcopy(dict(value))
    artifact.pop("artifact_hash", None)
    return artifact


def build_generation_artifact(
    candidate: Mapping[str, Any],
    *,
    run_id: str,
    job_id: str,
    topic_id: str,
    provider: Mapping[str, Any],
    settings: Mapping[str, Any] | None = None,
    attempt: int = 1,
) -> dict[str, Any]:
    provider_row = dict(provider)
    settings_row = dict(settings or {})
    recovery = provider_row.get("structured_recovery")
    recovery = dict(recovery) if isinstance(recovery, Mapping) else {}
    parsed_hash = _authored_payload_hash(candidate)
    raw_hash = str(
        provider_row.get("raw_response_hash")
        or provider_row.get("provider_response_hash")
        or recovery.get("original_candidate_hash")
        or ""
    )
    raw_hash_kind = "provider_response"
    if not raw_hash:
        raw_hash = parsed_hash
        raw_hash_kind = "authored_payload_fallback"
    transformations: list[str] = []
    method = str(recovery.get("method") or "")
    if method:
        transformations.append(method)
    transformations.extend(str(value) for value in recovery.get("repair_codes") or ())
    identity = {
        "run_id": run_id,
        "job_id": job_id,
        "topic_id": topic_id,
        "authored_payload_hash": parsed_hash,
        "provider": str(provider_row.get("provider") or ""),
        "model": str(provider_row.get("model") or ""),
    }
    artifact = {
        "schema_version": "rpg_world_generation_artifact_v1",
        "generation_artifact_id": "genart:" + content_hash(identity)[:32],
        "generation_run_id": run_id,
        "job_id": job_id,
        "topic_id": topic_id,
        "provider": str(provider_row.get("provider") or ""),
        "model": str(provider_row.get("model") or ""),
        "generator": str(provider_row.get("generator") or ""),
        "generator_version": str(settings_row.get("generator_version") or ""),
        "prompt_version": str(settings_row.get("prompt_version") or ""),
        "raw_response_hash": raw_hash,
        "raw_response_hash_kind": raw_hash_kind,
        "parsed_payload_hash": parsed_hash,
        "attempt": max(1, int(attempt or 1)),
        "authorship_class": AuthorshipClass.LLM_AUTHORED.value,
        "transformations": list(dict.fromkeys(transformations)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact["artifact_hash"] = content_hash(_artifact_without_hash(artifact))
    return artifact


def attach_server_llm_authorship(
    candidate: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    payload = attach_llm_authorship(candidate, artifact)
    provenance = dict(payload.get("provenance") or {})
    authorship = dict(provenance.get("authorship") or {})
    authorship["generation_artifact"] = dict(artifact)
    provenance["authorship"] = authorship
    payload["provenance"] = provenance
    return payload


def generation_artifact(candidate: Mapping[str, Any]) -> dict[str, Any]:
    provenance = candidate.get("provenance")
    provenance = dict(provenance) if isinstance(provenance, Mapping) else {}
    authorship = provenance.get("authorship")
    authorship = dict(authorship) if isinstance(authorship, Mapping) else {}
    artifact = authorship.get("generation_artifact")
    return dict(artifact) if isinstance(artifact, Mapping) else {}


def validate_publishable_authorship(
    candidate: Mapping[str, Any],
    *,
    server_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify origins, artifact integrity, and exact authored-string payload hashes."""

    artifact = dict(server_artifact or {})
    origin_report = _validate_origins(candidate, server_artifact=None)
    blockers = [
        dict(row)
        for row in origin_report.get("blocked_paths") or ()
        if str(dict(row).get("code") or "") != "server_generation_artifact_missing"
    ]
    leaves = lore_string_leaves(candidate)
    llm_origins = [
        row
        for row in dict(dict(candidate.get("provenance") or {}).get("authorship") or {}).get("origin_ledger") or ()
        if isinstance(row, Mapping)
        and str(row.get("authorship_class") or "") == AuthorshipClass.LLM_AUTHORED.value
    ]
    if llm_origins:
        if not artifact:
            blockers.append({"path": "/provenance/authorship", "code": "server_generation_artifact_missing"})
        else:
            expected_artifact_hash = content_hash(_artifact_without_hash(artifact))
            if str(artifact.get("artifact_hash") or "") != expected_artifact_hash:
                blockers.append({"path": "/provenance/authorship", "code": "generation_artifact_hash_mismatch"})
            if str(artifact.get("parsed_payload_hash") or "") != _authored_payload_hash(candidate):
                blockers.append({"path": "/", "code": "generation_artifact_payload_hash_mismatch"})
            if not str(artifact.get("provider") or "") or not str(artifact.get("model") or ""):
                blockers.append({"path": "/provenance/authorship", "code": "generation_artifact_provider_or_model_missing"})
            if str(artifact.get("authorship_class") or "") != AuthorshipClass.LLM_AUTHORED.value:
                blockers.append({"path": "/provenance/authorship", "code": "generation_artifact_not_llm_authored"})
            artifact_id = str(artifact.get("generation_artifact_id") or "")
            for origin in llm_origins:
                if str(origin.get("generation_artifact_id") or "") != artifact_id:
                    blockers.append({"path": str(origin.get("path") or "/"), "code": "origin_artifact_mismatch"})

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for blocker in blockers:
        unique[(str(blocker.get("path") or ""), str(blocker.get("code") or ""))] = blocker
    ordered = [unique[key] for key in sorted(unique)]
    return {
        "schema_version": "rpg_world_publishable_authorship_report_v1",
        "publishable": not ordered,
        "lore_string_count": len(leaves),
        "origin_count": int(origin_report.get("origin_count") or 0),
        "generation_artifact_id": str(artifact.get("generation_artifact_id") or ""),
        "blocked_paths": ordered,
    }


def require_publishable_authorship(
    candidate: Mapping[str, Any],
    *,
    server_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report = validate_publishable_authorship(candidate, server_artifact=server_artifact)
    if not report["publishable"]:
        raise AuthorshipValidationError(report)
    return report


__all__ = [
    "AuthorshipClass",
    "AuthorshipValidationError",
    "attach_human_authorship",
    "attach_server_llm_authorship",
    "build_generation_artifact",
    "generation_artifact",
    "prove_structural_repair_non_authoring",
    "require_publishable_authorship",
    "validate_publishable_authorship",
]
