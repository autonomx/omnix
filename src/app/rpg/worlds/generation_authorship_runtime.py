"""Runtime artifact verification built on immutable World Forge topic results."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from .generation_authorship import (
    AuthorshipClass,
    AuthorshipValidationError,
    attach_human_authorship as _attach_human_authorship,
    attach_llm_authorship,
    content_hash,
    lore_string_leaves as _base_lore_string_leaves,
    prove_structural_repair_non_authoring,
    validate_publishable_authorship as _validate_origins,
)

_MACHINE_FACT_FIELDS = {
    "id",
    "subject",
    "predicate",
    "object",
    "authority",
    "approved_authority",
    "visibility",
    "entity_refs",
    "topic_id",
    "field_id",
    "value_type",
    "semantic_role",
    "source",
    "authorship_class",
    "lookup",
    "lookup_schema",
}
_MACHINE_ORIGIN_BLOCKER_CODES = {
    "authorship_class_not_publishable",
    "server_generation_artifact_missing",
    "origin_artifact_mismatch",
    "human_authorship_event_missing",
}


def _machine_structured_fact_paths(candidate: Mapping[str, Any]) -> set[str]:
    paths: set[str] = set()
    facts = candidate.get("facts")
    if not isinstance(facts, (list, tuple)):
        return paths
    for index, value in enumerate(facts):
        if not isinstance(value, Mapping):
            continue
        row = dict(value)
        machine = (
            str(row.get("authorship_class") or "")
            == AuthorshipClass.MACHINE_STRUCTURED.value
            or str(row.get("source") or "").startswith(
                "profile_structured_fact_compiler_"
            )
        )
        if not machine:
            continue
        prefix = f"/facts/{index}/"
        for leaf in _base_lore_string_leaves({"facts": [row]}):
            path = str(leaf["path"])
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 3 and parts[2] in _MACHINE_FACT_FIELDS:
                suffix = "/".join(parts[2:])
                paths.add(prefix + suffix)
    return paths


def lore_string_leaves(candidate: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    machine_paths = _machine_structured_fact_paths(candidate)
    return tuple(
        row
        for row in _base_lore_string_leaves(candidate)
        if str(row["path"]) not in machine_paths
    )


def _reclassify_machine_origins(candidate: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(candidate))
    machine_paths = _machine_structured_fact_paths(payload)
    provenance = dict(payload.get("provenance") or {})
    authorship = dict(provenance.get("authorship") or {})
    ledger: list[dict[str, Any]] = []
    for value in authorship.get("origin_ledger") or ():
        if not isinstance(value, Mapping):
            continue
        row = dict(value)
        if str(row.get("path") or "") in machine_paths:
            row.update(
                {
                    "authorship_class": AuthorshipClass.MACHINE_STRUCTURED.value,
                    "generation_artifact_id": "",
                    "human_edit_event_id": "",
                }
            )
            row.pop("parent_origin", None)
        ledger.append(row)
    authorship["origin_ledger"] = ledger
    provenance["authorship"] = authorship
    payload["provenance"] = provenance
    return payload


def _authored_payload_rows(candidate: Mapping[str, Any]) -> list[dict[str, str]]:
    return sorted(
        [
            {"path": str(row["path"]), "content_hash": str(row["content_hash"])}
            for row in lore_string_leaves(candidate)
        ],
        key=lambda row: (row["path"], row["content_hash"]),
    )


def _authored_payload_hash(candidate: Mapping[str, Any]) -> str:
    return content_hash(_authored_payload_rows(candidate))


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
        or recovery.get("accepted_response_hash")
        or recovery.get("original_candidate_hash")
        or ""
    )
    raw_hash_kind = str(
        provider_row.get("raw_response_hash_kind") or "provider_response"
    )
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
    payload = _reclassify_machine_origins(attach_llm_authorship(candidate, artifact))
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


def attach_human_authorship(
    candidate: Mapping[str, Any],
    *,
    event_id: str,
    prior_candidate: Mapping[str, Any] | None = None,
    edited_llm: bool = False,
) -> dict[str, Any]:
    """Attach human origins and retain the immutable provider artifact for mixed lore."""

    prior = dict(prior_candidate or {})
    artifact = generation_artifact(prior)
    payload = _reclassify_machine_origins(
        _attach_human_authorship(
            candidate,
            event_id=event_id,
            prior_candidate=prior,
            edited_llm=edited_llm,
        )
    )
    if artifact:
        provenance = dict(payload.get("provenance") or {})
        authorship = dict(provenance.get("authorship") or {})
        authorship["generation_artifact"] = artifact
        provenance["authorship"] = authorship
        payload["provenance"] = provenance
    return payload


def _artifact_origin_hash(
    candidate: Mapping[str, Any],
    artifact_id: str,
) -> str:
    authorship = dict(dict(candidate.get("provenance") or {}).get("authorship") or {})
    rows: list[dict[str, str]] = []
    for value in authorship.get("origin_ledger") or ():
        if not isinstance(value, Mapping):
            continue
        row = dict(value)
        path = str(row.get("path") or "")
        if (
            str(row.get("authorship_class") or "")
            == AuthorshipClass.LLM_AUTHORED.value
            and str(row.get("generation_artifact_id") or "") == artifact_id
        ):
            rows.append({"path": path, "content_hash": str(row.get("content_hash") or "")})
            continue
        parent = row.get("parent_origin")
        if not isinstance(parent, Mapping):
            continue
        if (
            str(parent.get("authorship_class") or "")
            == AuthorshipClass.LLM_AUTHORED.value
            and str(parent.get("generation_artifact_id") or "") == artifact_id
        ):
            rows.append({"path": path, "content_hash": str(parent.get("content_hash") or "")})
    return content_hash(
        sorted(rows, key=lambda row: (row["path"], row["content_hash"]))
    )


def validate_publishable_authorship(
    candidate: Mapping[str, Any],
    *,
    server_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify origins, artifact integrity, and exact authored-string hashes."""

    artifact = dict(server_artifact or generation_artifact(candidate) or {})
    machine_paths = _machine_structured_fact_paths(candidate)
    origin_report = _validate_origins(candidate, server_artifact=None)
    blockers = [
        dict(row)
        for row in origin_report.get("blocked_paths") or ()
        if str(dict(row).get("code") or "") != "server_generation_artifact_missing"
        and not (
            str(dict(row).get("path") or "") in machine_paths
            and str(dict(row).get("code") or "") in _MACHINE_ORIGIN_BLOCKER_CODES
        )
    ]
    leaves = lore_string_leaves(candidate)
    llm_origins = [
        row
        for row in dict(
            dict(candidate.get("provenance") or {}).get("authorship") or {}
        ).get("origin_ledger")
        or ()
        if isinstance(row, Mapping)
        and (
            str(row.get("authorship_class") or "")
            == AuthorshipClass.LLM_AUTHORED.value
            or str(dict(row.get("parent_origin") or {}).get("authorship_class") or "")
            == AuthorshipClass.LLM_AUTHORED.value
        )
    ]
    if llm_origins:
        if not artifact:
            blockers.append(
                {"path": "/provenance/authorship", "code": "server_generation_artifact_missing"}
            )
        else:
            expected_artifact_hash = content_hash(_artifact_without_hash(artifact))
            if str(artifact.get("artifact_hash") or "") != expected_artifact_hash:
                blockers.append(
                    {"path": "/provenance/authorship", "code": "generation_artifact_hash_mismatch"}
                )
            artifact_id = str(artifact.get("generation_artifact_id") or "")
            if str(artifact.get("parsed_payload_hash") or "") != _artifact_origin_hash(
                candidate, artifact_id
            ):
                blockers.append(
                    {"path": "/", "code": "generation_artifact_payload_hash_mismatch"}
                )
            if not str(artifact.get("provider") or "") or not str(artifact.get("model") or ""):
                blockers.append(
                    {
                        "path": "/provenance/authorship",
                        "code": "generation_artifact_provider_or_model_missing",
                    }
                )
            if str(artifact.get("authorship_class") or "") != AuthorshipClass.LLM_AUTHORED.value:
                blockers.append(
                    {
                        "path": "/provenance/authorship",
                        "code": "generation_artifact_not_llm_authored",
                    }
                )
            for origin in llm_origins:
                current_id = str(origin.get("generation_artifact_id") or "")
                parent_id = str(
                    dict(origin.get("parent_origin") or {}).get("generation_artifact_id")
                    or ""
                )
                if artifact_id not in {current_id, parent_id}:
                    blockers.append(
                        {
                            "path": str(origin.get("path") or "/"),
                            "code": "origin_artifact_mismatch",
                        }
                    )

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for blocker in blockers:
        unique[(str(blocker.get("path") or ""), str(blocker.get("code") or ""))] = blocker
    ordered = [unique[key] for key in sorted(unique)]
    ledger = dict(
        dict(candidate.get("provenance") or {}).get("authorship") or {}
    ).get("origin_ledger") or ()
    authored_origin_count = sum(
        1
        for row in ledger
        if isinstance(row, Mapping)
        and str(row.get("authorship_class") or "")
        != AuthorshipClass.MACHINE_STRUCTURED.value
    )
    return {
        "schema_version": "rpg_world_publishable_authorship_report_v1",
        "publishable": not ordered,
        "lore_string_count": len(leaves),
        "origin_count": authored_origin_count,
        "machine_structured_string_count": len(machine_paths),
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
    "lore_string_leaves",
    "prove_structural_repair_non_authoring",
    "require_publishable_authorship",
    "validate_publishable_authorship",
]
