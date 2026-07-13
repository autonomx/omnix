"""Complete extraction of legacy Omnix persistence into one verified bundle."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cutover import LEGACY_BUNDLE_FORMAT, bundle_hash


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _rows(path: Path | None, table: str) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if exists is None:
            return []
        return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"').fetchall()]
    finally:
        connection.close()


def _character_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": str(row.get("display_name") or ""),
        "description": str(row.get("description") or ""),
        "personality_prompt": str(row.get("personality_prompt") or ""),
        "default_greeting": str(row.get("default_greeting") or ""),
        "default_voice_asset_id": row.get("default_voice_asset_id"),
        "speech_style": _json(row.get("speech_style_json"), {}),
        "identity_policy": _json(row.get("identity_policy_json"), {}),
        "shared_memory_policy": _json(row.get("shared_memory_policy_json"), {}),
    }


def _characters(path: Path | None) -> list[dict[str, Any]]:
    versions: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(path, "character_profile_versions"):
        character_id = str(row.get("character_id") or "")
        versions.setdefault(character_id, []).append(
            {"version": int(row.get("version") or 1), "profile": _character_profile(row)}
        )
    segments = []
    for row in _rows(path, "conversation_segments"):
        segments.append(
            {
                "id": str(row.get("id") or ""),
                "session_id": str(row.get("session_id") or ""),
                "interaction_mode": str(row.get("interaction_mode") or "system"),
                "character_id": row.get("character_id"),
                "character_version": row.get("character_profile_version") or row.get("character_version"),
                "transcript_policy": str(row.get("transcript_policy") or "persistent"),
                "read_memory": bool(row.get("read_memory", 0)),
                "write_memory": bool(row.get("write_memory", 0)),
                "shared_memory_access": str(row.get("shared_memory_access") or "none"),
                "carryover_summary": row.get("carryover_summary"),
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
            }
        )
    result: list[dict[str, Any]] = []
    for row in _rows(path, "character_profiles"):
        character_id = str(row.get("id") or "").strip()
        if not character_id:
            continue
        result.append(
            {
                "id": character_id,
                "profile": _character_profile(row),
                "visibility": str(row.get("visibility") or "private"),
                "enabled": bool(row.get("enabled", 1)),
                "versions": sorted(versions.get(character_id, []), key=lambda item: item["version"]),
                "conversation_segments": [
                    item for item in segments if item.get("character_id") == character_id
                ],
            }
        )
    unowned = [item for item in segments if not item.get("character_id")]
    if unowned:
        result.append(
            {
                "id": "character:migration-envelope",
                "_migration_envelope": True,
                "conversation_segments": unowned,
            }
        )
    return result


def _memory(path: Path | None) -> list[dict[str, Any]]:
    records = []
    for row in _rows(path, "memory_records"):
        memory_id = str(row.get("id") or "").strip()
        if not memory_id:
            continue
        records.append(
            {
                "id": memory_id,
                "owner_type": str(row.get("scope") or "workspace"),
                "owner_id": str(row.get("scope_id") or "workspace:local"),
                "category": str(row.get("category") or "fact"),
                "content": str(row.get("content") or ""),
                "normalized_content": str(row.get("normalized_content") or row.get("content") or "").strip().lower(),
                "confidence": float(row.get("confidence") or 1.0),
                "pinned": bool(row.get("pinned", 0)),
                "trust_level": str(row.get("trust_level") or "unverified_import"),
                "sensitivity": str(row.get("sensitivity") or "normal"),
                "provenance_type": row.get("provenance_type") or "import",
                "provenance_id": row.get("provenance_id"),
                "source": str(row.get("source") or "imported"),
                "status": str(row.get("status") or "active"),
                "expires_at": row.get("expires_at"),
            }
        )
    candidates = []
    for row in _rows(path, "memory_candidates"):
        candidates.append(
            {
                "id": str(row.get("id") or ""),
                "source_session_id": row.get("source_session_id"),
                "source_message_id": str(row.get("source_message_id") or ""),
                "candidate_fingerprint": str(row.get("candidate_fingerprint") or ""),
                "proposed_owner_type": str(row.get("proposed_scope") or "workspace"),
                "proposed_owner_id": str(row.get("proposed_scope_id") or "workspace:local"),
                "proposed_category": str(row.get("proposed_category") or "fact"),
                "proposed_content": str(row.get("proposed_content") or ""),
                "confidence": float(row.get("confidence") or 0.5),
                "source": str(row.get("source") or "imported"),
                "trust_level": str(row.get("trust_level") or "unverified_import"),
                "sensitivity": str(row.get("sensitivity") or "normal"),
                "extraction_metadata": _json(row.get("extraction_metadata_json"), {}),
                "status": str(row.get("status") or "pending"),
                "created_at": row.get("created_at"),
                "resolved_at": row.get("resolved_at"),
            }
        )
    items_by_snapshot: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(path, "memory_snapshot_items"):
        items_by_snapshot.setdefault(str(row.get("snapshot_id") or ""), []).append(
            {
                "memory_record_id": str(row.get("memory_record_id") or ""),
                "position": int(row.get("position") or 0),
                "record_revision": int(row.get("record_revision") or 1),
                "frozen_content": str(row.get("frozen_content") or ""),
                "revoked_at": row.get("revoked_at"),
            }
        )
    snapshots = []
    for row in _rows(path, "memory_snapshots"):
        snapshot_id = str(row.get("id") or "")
        snapshots.append(
            {
                "id": snapshot_id,
                "session_id": str(row.get("session_id") or ""),
                "owner_type": str(row.get("owner_type") or "system"),
                "owner_id": str(row.get("owner_id") or "system-assistant"),
                "revision": int(row.get("revision") or 1),
                "token_estimate": int(row.get("token_estimate") or 0),
                "created_at": row.get("created_at"),
                "refreshed_at": row.get("refreshed_at"),
                "items": sorted(items_by_snapshot.get(snapshot_id, []), key=lambda item: item["position"]),
            }
        )
    events = [
        {
            "id": str(row.get("id") or ""),
            "entity_type": str(row.get("entity_type") or "memory"),
            "entity_id": str(row.get("entity_id") or ""),
            "event_type": str(row.get("event_type") or "legacy.event"),
            "payload": _json(row.get("metadata_json"), {}),
            "created_at": row.get("created_at"),
        }
        for row in _rows(path, "memory_events")
    ]
    if candidates or snapshots or events:
        records.append(
            {
                "id": "memory:migration-envelope",
                "_migration_envelope": True,
                "candidates": candidates,
                "snapshots": snapshots,
                "events": events,
            }
        )
    return records


def _chat_sessions(path: Path | None) -> list[dict[str, Any]]:
    messages_by_session: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(path, "chat_messages"):
        session_id = str(row.get("session_id") or "")
        messages_by_session.setdefault(session_id, []).append(
            {
                "id": str(row.get("id") or ""),
                "role": str(row.get("role") or "user"),
                "content": str(row.get("content") or ""),
                "created_at": row.get("created_at"),
                "metadata": _json(row.get("metadata_json"), {}),
                "_position": int(row.get("position") or 0),
            }
        )
    result = []
    for row in _rows(path, "chat_sessions"):
        session_id = str(row.get("id") or "").strip()
        if not session_id:
            continue
        messages = sorted(messages_by_session.get(session_id, []), key=lambda item: item["_position"])
        for message in messages:
            message.pop("_position", None)
        result.append(
            {
                "id": session_id,
                "title": str(row.get("title") or "Imported chat"),
                "provider_id": row.get("provider_id"),
                "model_id": row.get("model_id"),
                "project_id": row.get("project_id"),
                "profile_id": row.get("profile_id"),
                "interaction_mode": str(row.get("interaction_mode") or "system"),
                "character_id": row.get("character_id"),
                "character_version": row.get("character_profile_version"),
                "memory_enabled": bool(row.get("memory_enabled", 0)),
                "memory_snapshot_id": row.get("memory_snapshot_id"),
                "transcript_policy": str(row.get("transcript_policy") or "persistent"),
                "active_segment_id": row.get("active_segment_id"),
                "settings": {
                    "research_mode_override": row.get("research_mode_override"),
                    "read_memory": bool(row.get("read_memory", 0)),
                    "write_memory": bool(row.get("write_memory", 0)),
                    "shared_memory_access": row.get("shared_memory_access") or "none",
                    "voice_asset_id": row.get("voice_asset_id"),
                    "effective_identity_hash": row.get("effective_identity_hash"),
                },
                "messages": messages,
            }
        )
    return result


def _jobs(path: Path | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events_by_job: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(path, "job_events"):
        events_by_job.setdefault(str(row.get("job_id") or ""), []).append(
            {
                "event_type": str(row.get("event_type") or "legacy.event"),
                "payload": _json(row.get("payload_json"), {}),
                "created_at": row.get("created_at"),
            }
        )
    jobs = []
    for row in _rows(path, "jobs"):
        job_id = str(row.get("id") or "").strip()
        if not job_id:
            continue
        lease = _json(row.get("lease_json"), {})
        jobs.append(
            {
                "id": job_id,
                "module": str(row.get("module") or "legacy"),
                "job_type": str(row.get("type") or "legacy"),
                "resource_class": str(row.get("resource_class") or "cpu"),
                "priority": int(row.get("priority") or 0),
                "status": str(row.get("status") or "queued"),
                "input_payload": _json(row.get("input_payload_json"), {}),
                "output_refs": _json(row.get("output_refs_json"), []),
                "progress": _json(row.get("progress_json"), {}),
                "error": _json(row.get("error_json"), None),
                "attempt_count": int(_json(row.get("compat_json"), {}).get("attempt_count") or 0),
                "max_attempts": int(_json(row.get("compat_json"), {}).get("max_attempts") or 3),
                "completed_at": row.get("completed_at"),
                "metadata": {
                    "legacy_compat": _json(row.get("compat_json"), {}),
                    "stages": _json(row.get("stages_json"), []),
                    "logs": _json(row.get("logs_json"), []),
                    "input_ref": _json(row.get("input_ref_json"), None),
                    "cancel": _json(row.get("cancel_json"), {}),
                    "lease": lease,
                },
                "events": events_by_job.get(job_id, []),
            }
        )
    submissions = []
    for row in _rows(path, "rpg_foreground_submissions"):
        submissions.append(
            {
                "session_id": str(row.get("session_id") or ""),
                "submission_id": str(row.get("submission_id") or ""),
                "status": str(row.get("status") or "claimed"),
                "claim_token": str(row.get("claim_token") or "legacy"),
                "job_id": row.get("job_id"),
                "response": _json(row.get("result_json"), None),
                "error": row.get("error_text"),
                "lease_expires_at": row.get("lease_expires_at"),
                "execution_started_at": row.get("execution_started_at"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
        )
    return jobs, submissions


def _interaction_events(path: Path) -> list[dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                envelope = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event = envelope.get("event") if isinstance(envelope, dict) else None
            if isinstance(event, dict):
                key = str(event.get("interaction_id") or f"sequence:{event.get('sequence')}")
                events[key] = event
    return sorted(events.values(), key=lambda item: int(item.get("sequence") or 0))


def _rpg_campaigns(directory: Path | None, submissions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if directory is None or not directory.is_dir():
        return []
    result = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".interactions.json"):
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        session = raw.get("session") if isinstance(raw.get("session"), dict) else raw
        if not isinstance(session, dict):
            continue
        manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
        runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
        campaign_id = str(manifest.get("session_id") or manifest.get("id") or path.stem).strip()
        timeline = runtime.get("interaction_timeline") if isinstance(runtime.get("interaction_timeline"), dict) else {}
        interactions = {
            str(item.get("interaction_id") or f"sequence:{item.get('sequence')}"): dict(item)
            for item in timeline.get("events", [])
            if isinstance(item, dict)
        }
        for item in _interaction_events(path.with_suffix(".interactions.jsonl")):
            interactions[str(item.get("interaction_id") or f"sequence:{item.get('sequence')}")] = item
        result.append(
            {
                "id": campaign_id,
                "title": str(manifest.get("title") or campaign_id),
                "revision": int(runtime.get("state_revision") or manifest.get("turn_count") or 0),
                "state": session,
                "engine_version": str(manifest.get("engine_version") or session.get("engine_version") or "legacy"),
                "schema_version": str(raw.get("save_version") or session.get("save_version") or "legacy"),
                "seed": str(manifest.get("seed") or session.get("seed") or "legacy"),
                "status": "archived" if manifest.get("archived") else "active",
                "metadata": {"legacy_path": str(path)},
                "interactions": sorted(interactions.values(), key=lambda item: int(item.get("sequence") or 0)),
                "foreground_submissions": [
                    item for item in submissions if item.get("session_id") == campaign_id
                ],
            }
        )
    return result


def _assets(path: Path | None) -> list[dict[str, Any]]:
    source = _read_json(path, {})
    source = source.get("assets") if isinstance(source, dict) and isinstance(source.get("assets"), dict) else source
    if not isinstance(source, dict):
        return []
    result = []
    for asset_id, raw_payload in sorted(source.items()):
        payload = dict(raw_payload or {})
        source_path = str(payload.get("storage_path") or payload.get("path") or "")
        if source_path:
            result.append(
                {
                    "id": str(asset_id),
                    "module": str(payload.get("module") or "legacy"),
                    "asset_type": str(payload.get("type") or payload.get("asset_type") or "report"),
                    "mime_type": str(payload.get("mime_type") or "application/octet-stream"),
                    "source_path": source_path,
                    "metadata": dict(payload.get("metadata") or {}),
                    "compat": {**dict(payload.get("compat") or {}), "legacy_manifest": str(path)},
                }
            )
    return result


def _read_json(path: Path | None, default: Any) -> Any:
    if path is None or not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _list_json(path: Path | None, key: str) -> list[dict[str, Any]]:
    value = _read_json(path, [])
    if isinstance(value, dict):
        value = value.get(key, value.get("records", []))
    return [dict(item) for item in value] if isinstance(value, list) else []


def _file_inventory(paths: dict[str, str]) -> list[dict[str, Any]]:
    records = []
    for name, raw in sorted(paths.items()):
        path = Path(raw) if raw else None
        if path is None or not path.exists():
            records.append({"name": name, "path": raw, "exists": False})
            continue
        if path.is_file():
            content = path.read_bytes()
            records.append(
                {
                    "name": name,
                    "path": str(path),
                    "exists": True,
                    "kind": "file",
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        else:
            files = sorted(item for item in path.rglob("*") if item.is_file())
            digest = hashlib.sha256()
            total = 0
            for item in files:
                data = item.read_bytes()
                relative = item.relative_to(path).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(data)
                total += len(data)
            records.append(
                {
                    "name": name,
                    "path": str(path),
                    "exists": True,
                    "kind": "directory",
                    "files": len(files),
                    "bytes": total,
                    "sha256": digest.hexdigest(),
                }
            )
    return records


def build_bundle(args: Namespace) -> dict[str, Any]:
    jobs, submissions = _jobs(getattr(args, "jobs_db", None))
    source_paths = {
        "asset_manifest": str(getattr(args, "asset_manifest", None) or ""),
        "character_db": str(getattr(args, "character_db", None) or ""),
        "memory_db": str(getattr(args, "memory_db", None) or ""),
        "chat_db": str(getattr(args, "chat_db", None) or ""),
        "jobs_db": str(getattr(args, "jobs_db", None) or ""),
        "rpg_sessions_dir": str(getattr(args, "rpg_sessions_dir", None) or ""),
        "settings_json": str(getattr(args, "settings_json", None) or ""),
        "providers_json": str(getattr(args, "providers_json", None) or ""),
        "prompts_json": str(getattr(args, "prompts_json", None) or ""),
        "research_json": str(getattr(args, "research_json", None) or ""),
        "reports_json": str(getattr(args, "reports_json", None) or ""),
        "module_records_json": str(getattr(args, "module_records_json", None) or ""),
    }
    bundle: dict[str, Any] = {
        "format_version": LEGACY_BUNDLE_FORMAT,
        "source_id": args.source_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entities": {
            "assets": _assets(getattr(args, "asset_manifest", None)),
            "characters": _characters(getattr(args, "character_db", None)),
            "memory_records": _memory(getattr(args, "memory_db", None)),
            "chat_sessions": _chat_sessions(getattr(args, "chat_db", None)),
            "jobs": jobs,
            "rpg_campaigns": _rpg_campaigns(getattr(args, "rpg_sessions_dir", None), submissions),
            "settings": _list_json(getattr(args, "settings_json", None), "settings"),
            "providers": _list_json(getattr(args, "providers_json", None), "providers"),
            "prompts": _list_json(getattr(args, "prompts_json", None), "prompts"),
            "research_records": _list_json(getattr(args, "research_json", None), "research_records"),
            "reports": _list_json(getattr(args, "reports_json", None), "reports"),
            "module_records": _list_json(getattr(args, "module_records_json", None), "module_records"),
        },
        "source_paths": source_paths,
        "source_inventory": _file_inventory(source_paths),
    }
    bundle["source_hash"] = bundle_hash(bundle)
    return bundle
