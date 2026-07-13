from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.persistence.cutover import LEGACY_BUNDLE_FORMAT, bundle_hash, preflight_bundle


def _json_value(value: Any, default: Any) -> Any:
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


def _characters(path: Path | None) -> list[dict[str, Any]]:
    profiles = _rows(path, "character_profiles")
    versions_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(path, "character_profile_versions"):
        character_id = str(row.get("character_id") or "")
        profile = _character_profile(row)
        versions_by_id.setdefault(character_id, []).append(
            {"version": int(row.get("version") or 1), "profile": profile}
        )
    results: list[dict[str, Any]] = []
    for row in profiles:
        character_id = str(row.get("id") or "").strip()
        if not character_id:
            continue
        results.append(
            {
                "id": character_id,
                "profile": _character_profile(row),
                "visibility": str(row.get("visibility") or "private"),
                "enabled": bool(row.get("enabled", 1)),
                "versions": sorted(
                    versions_by_id.get(character_id, []), key=lambda item: item["version"]
                ),
            }
        )
    return results


def _character_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": str(row.get("display_name") or ""),
        "description": str(row.get("description") or ""),
        "personality_prompt": str(row.get("personality_prompt") or ""),
        "default_greeting": str(row.get("default_greeting") or ""),
        "default_voice_asset_id": row.get("default_voice_asset_id"),
        "speech_style": _json_value(row.get("speech_style_json"), {}),
        "identity_policy": _json_value(row.get("identity_policy_json"), {}),
        "shared_memory_policy": _json_value(row.get("shared_memory_policy_json"), {}),
    }


def _memory_records(path: Path | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in _rows(path, "memory_records"):
        memory_id = str(row.get("id") or "").strip()
        if not memory_id:
            continue
        owner_type = str(row.get("owner_type") or row.get("scope") or "user")
        owner_id = str(row.get("owner_id") or row.get("scope_id") or "user:local")
        results.append(
            {
                "id": memory_id,
                "owner_type": owner_type,
                "owner_id": owner_id,
                "category": str(row.get("category") or "general"),
                "content": str(row.get("content") or ""),
                "normalized_content": str(
                    row.get("normalized_content") or str(row.get("content") or "").strip().lower()
                ),
                "confidence": float(row.get("confidence") or 1.0),
                "pinned": bool(row.get("pinned", 0)),
                "trust_level": str(row.get("trust_level") or "normal"),
                "sensitivity": str(row.get("sensitivity") or "normal"),
                "provenance_type": row.get("provenance_type"),
                "provenance_id": row.get("provenance_id"),
                "source": str(row.get("source") or "legacy"),
                "status": str(row.get("status") or "active"),
                "expires_at": row.get("expires_at"),
            }
        )
    return results


def _chat_sessions(path: Path | None) -> list[dict[str, Any]]:
    sessions = _rows(path, "chat_sessions")
    messages_by_session: dict[str, list[dict[str, Any]]] = {}
    for row in _rows(path, "chat_messages"):
        session_id = str(row.get("session_id") or "")
        message_id = str(row.get("id") or "").strip()
        if not session_id or not message_id:
            continue
        messages_by_session.setdefault(session_id, []).append(
            {
                "id": message_id,
                "role": str(row.get("role") or "user"),
                "content": str(row.get("content") or ""),
                "created_at": row.get("created_at"),
                "metadata": _json_value(row.get("metadata_json"), {}),
                "_position": int(row.get("position") or 0),
            }
        )
    results: list[dict[str, Any]] = []
    for row in sessions:
        session_id = str(row.get("id") or "").strip()
        if not session_id:
            continue
        messages = sorted(messages_by_session.get(session_id, []), key=lambda item: item["_position"])
        for message in messages:
            message.pop("_position", None)
        settings = {
            "research_mode_override": row.get("research_mode_override"),
            "read_memory": bool(row.get("read_memory", 0)),
            "write_memory": bool(row.get("write_memory", 0)),
            "shared_memory_access": row.get("shared_memory_access") or "none",
            "voice_asset_id": row.get("voice_asset_id"),
            "effective_identity_hash": row.get("effective_identity_hash"),
        }
        results.append(
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
                "settings": settings,
                "messages": messages,
            }
        )
    return results


def _jobs(path: Path | None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in _rows(path, "jobs"):
        job_id = str(row.get("id") or "").strip()
        if not job_id:
            continue
        results.append(
            {
                "id": job_id,
                "module": str(row.get("module") or "legacy"),
                "job_type": str(row.get("type") or row.get("job_type") or "legacy"),
                "resource_class": str(row.get("resource_class") or "cpu"),
                "priority": int(row.get("priority") or 0),
                "status": str(row.get("status") or "queued"),
                "input_payload": _json_value(row.get("input_payload_json"), {}),
                "output_refs": _json_value(row.get("output_refs_json"), []),
                "progress": _json_value(row.get("progress_json"), {}),
                "error": _json_value(row.get("error_json"), None),
                "attempt_count": int(row.get("attempt_count") or 0),
                "max_attempts": int(row.get("max_attempts") or 3),
                "completed_at": row.get("completed_at"),
                "metadata": {"legacy_compat": _json_value(row.get("compat_json"), {})},
            }
        )
    return results


def _rpg_campaigns(directory: Path | None) -> list[dict[str, Any]]:
    if directory is None or not directory.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        session = raw.get("session") if isinstance(raw.get("session"), dict) else raw
        if not isinstance(session, dict):
            continue
        manifest = session.get("manifest") if isinstance(session.get("manifest"), dict) else {}
        runtime = session.get("runtime_state") if isinstance(session.get("runtime_state"), dict) else {}
        campaign_id = str(
            manifest.get("session_id") or manifest.get("id") or path.stem
        ).strip()
        if not campaign_id:
            continue
        results.append(
            {
                "id": campaign_id,
                "title": str(manifest.get("title") or campaign_id),
                "revision": int(runtime.get("state_revision") or manifest.get("turn_count") or 0),
                "state": session,
                "engine_version": str(
                    manifest.get("engine_version") or session.get("engine_version") or "legacy"
                ),
                "schema_version": str(raw.get("save_version") or "legacy"),
                "seed": str(manifest.get("seed") or session.get("seed") or "legacy"),
                "status": "archived" if manifest.get("archived") else "active",
                "metadata": {"legacy_path": str(path)},
            }
        )
    return results


def _assets(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    source = raw.get("assets") if isinstance(raw.get("assets"), dict) else raw
    if not isinstance(source, dict):
        return []
    results: list[dict[str, Any]] = []
    for asset_id, raw_payload in sorted(source.items()):
        payload = dict(raw_payload or {})
        source_path = str(payload.get("storage_path") or payload.get("path") or "")
        if not source_path:
            continue
        results.append(
            {
                "id": str(asset_id),
                "module": str(payload.get("module") or "legacy"),
                "asset_type": str(payload.get("type") or payload.get("asset_type") or "other"),
                "mime_type": str(payload.get("mime_type") or "application/octet-stream"),
                "source_path": source_path,
                "metadata": dict(payload.get("metadata") or {}),
                "compat": {
                    **dict(payload.get("compat") or {}),
                    "legacy_manifest": str(path),
                },
            }
        )
    return results


def build_bundle(args: argparse.Namespace) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "format_version": LEGACY_BUNDLE_FORMAT,
        "source_id": args.source_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "entities": {
            "assets": _assets(args.asset_manifest),
            "characters": _characters(args.character_db),
            "memory_records": _memory_records(args.memory_db),
            "chat_sessions": _chat_sessions(args.chat_db),
            "jobs": _jobs(args.jobs_db),
            "rpg_campaigns": _rpg_campaigns(args.rpg_sessions_dir),
        },
        "source_paths": {
            "asset_manifest": str(args.asset_manifest or ""),
            "character_db": str(args.character_db or ""),
            "memory_db": str(args.memory_db or ""),
            "chat_db": str(args.chat_db or ""),
            "jobs_db": str(args.jobs_db or ""),
            "rpg_sessions_dir": str(args.rpg_sessions_dir or ""),
        },
    }
    bundle["source_hash"] = bundle_hash(bundle)
    return bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export legacy Omnix persistence into a verified bundle")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument("--character-db", type=Path)
    parser.add_argument("--memory-db", type=Path)
    parser.add_argument("--chat-db", type=Path)
    parser.add_argument("--jobs-db", type=Path)
    parser.add_argument("--rpg-sessions-dir", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bundle = build_bundle(args)
    preflight = preflight_bundle(bundle)
    report = {
        "ok": preflight["ok"],
        "output": str(args.output),
        "source_id": preflight["source_id"],
        "source_hash": preflight["source_hash"],
        "counts": preflight["counts"],
        "errors": preflight["errors"],
    }
    if not preflight["ok"]:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
