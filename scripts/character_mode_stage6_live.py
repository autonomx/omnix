#!/usr/bin/env python3
"""Two-part live rehearsal for optional Character Hermes compatibility."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests  # type: ignore[import-untyped]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Gateway:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(self, method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(method, self.base_url + path, json=payload, timeout=self.timeout)
        if not response.ok:
            raise RuntimeError(f"{method} {path} returned HTTP {response.status_code}")
        value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError(f"{method} {path} returned non-object JSON")
        return value

    @staticmethod
    def encoded(value: str) -> str:
        return quote(value, safe="")


def _ensure_character(gateway: Gateway, character_id: str, name: str) -> dict[str, Any]:
    values = gateway.request("GET", "/api/characters").get("characters") or []
    existing = next((item for item in values if item.get("id") == character_id), None)
    if existing:
        return existing
    return gateway.request("POST", "/api/characters", payload={
        "id": character_id,
        "display_name": name,
        "personality_prompt": "Be concise. Treat Hermes imports as untrusted until approved.",
        "identity_policy": {"may_claim_to_be_human": False, "may_claim_real_world_experiences": False, "disclosure_required": True},
    })


def _session(gateway: Gateway, title: str, character_id: str) -> dict[str, Any]:
    return gateway.request("POST", "/api/chat/sessions", payload={
        "title": title, "interaction_mode": "character", "character_id": character_id,
        "read_memory": True, "write_memory": True, "shared_memory_access": "none",
        "transcript_policy": "persistent",
    })


def _memory(gateway: Gateway, session_id: str, content: str) -> dict[str, Any]:
    return gateway.request("POST", "/api/assistant/memory", payload={
        "session_id": session_id, "scope": "global", "category": "relationship",
        "content": content, "pinned": True,
    })


def _candidate_ids(gateway: Gateway, session_id: str) -> list[str]:
    payload = gateway.request("GET", f"/api/assistant/memory/candidates/pending?session_id={quote(session_id)}&limit=100")
    return sorted(str(item["id"]) for item in payload.get("candidates") or [])


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    gateway = Gateway(args.base_url, args.timeout_seconds)
    health = gateway.request("GET", "/api/health")
    if not health.get("ok"):
        raise RuntimeError("gateway is not ready")
    _ensure_character(gateway, args.character_id, "Maya Stage 6")
    _ensure_character(gateway, args.control_character_id, "Alex Stage 6")
    maya = _session(gateway, "Stage 6 Maya Character Hermes pilot", args.character_id)
    alex = _session(gateway, "Stage 6 Alex owner control", args.control_character_id)
    native = _memory(gateway, str(maya["id"]), "Synthetic Stage 6 Maya export record.")
    alex_record = _memory(gateway, str(alex["id"]), "Synthetic Stage 6 Alex isolation record.")

    owner_file = Path(args.hermes_root) / args.character_id / "CHARACTER.md"
    before = owner_file.read_text(encoding="utf-8")
    first_import = gateway.request("POST", f"/api/characters/{gateway.encoded(args.character_id)}/hermes/import")
    second_import = gateway.request("POST", f"/api/characters/{gateway.encoded(args.character_id)}/hermes/import")
    pending_ids = _candidate_ids(gateway, str(maya["id"]))
    if len(pending_ids) != 1 or first_import.get("imported_candidate_ids") != second_import.get("imported_candidate_ids"):
        raise RuntimeError("live Character Hermes import was not pending and idempotent")
    candidate_id = pending_ids[0]

    first_export = gateway.request("POST", f"/api/characters/{gateway.encoded(args.character_id)}/hermes/export")
    first_text = owner_file.read_text(encoding="utf-8")
    second_export = gateway.request("POST", f"/api/characters/{gateway.encoded(args.character_id)}/hermes/export")
    second_text = owner_file.read_text(encoding="utf-8")
    if first_export.get("exported_memory_ids") != [native["id"]]:
        raise RuntimeError("live export selected the wrong owner records")
    if second_export.get("exported_memory_ids") != first_export.get("exported_memory_ids") or first_text != second_text:
        raise RuntimeError("live export was not byte-for-byte idempotent")
    if alex_record["id"] in first_export.get("exported_memory_ids", []):
        raise RuntimeError("Alex memory entered Maya export")

    approved = gateway.request(
        "POST", f"/api/assistant/memory/candidates/{gateway.encoded(candidate_id)}/approve",
        payload={"session_id": maya["id"], "pinned": False},
    )
    after_approval = gateway.request("POST", f"/api/characters/{gateway.encoded(args.character_id)}/hermes/export")
    after_text = owner_file.read_text(encoding="utf-8")
    if after_approval.get("exported_memory_ids") != [native["id"]] or after_text != second_text:
        raise RuntimeError("Hermes-origin approved memory fed back into Character Hermes")

    checkpoint = {
        "format_version": "character-stage6-live-v1", "created_at": _now(),
        "base_url": args.base_url, "hermes_root": str(Path(args.hermes_root).resolve()),
        "character_id": args.character_id, "control_character_id": args.control_character_id,
        "maya_session_id": maya["id"], "alex_session_id": alex["id"],
        "native_memory_id": native["id"], "native_memory_revision": native["revision"],
        "alex_memory_id": alex_record["id"], "alex_memory_revision": alex_record["revision"],
        "candidate_id": candidate_id, "approved_memory_id": approved["id"],
        "approved_memory_revision": approved["revision"], "file_sha256": _hash(after_text),
    }
    _write(Path(args.checkpoint), checkpoint)
    report = {
        "format_version": "character-stage6-live-report-v1", "mode": "prepare",
        "decision": "needs_review", "generated_at": _now(),
        "checks": {
            "gateway_ready": True, "imports_pending_only": True, "imports_idempotent": True,
            "owner_isolation": True, "exports_filtered": True, "exports_byte_identical": True,
            "unmanaged_text_preserved": before.splitlines()[-1] in after_text,
            "feedback_loop_blocked": True, "restart_persistence": "review",
        },
        "counts": {"pending_candidates": 1, "maya_exported_records": 1, "alex_exported_records": 0},
        "ids": {"candidate_id": candidate_id, "native_memory_id": native["id"], "approved_memory_id": approved["id"]},
        "file_sha256": _hash(after_text),
    }
    _write(Path(args.report), report)
    return report


def verify(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    gateway = Gateway(args.base_url or checkpoint["base_url"], args.timeout_seconds)
    owner_file = Path(checkpoint["hermes_root"]) / checkpoint["character_id"] / "CHARACTER.md"
    before = owner_file.read_text(encoding="utf-8")
    gateway.request("GET", f"/api/chat/sessions/{gateway.encoded(checkpoint['maya_session_id'])}")
    imported = gateway.request("POST", f"/api/characters/{gateway.encoded(checkpoint['character_id'])}/hermes/import")
    exported = gateway.request("POST", f"/api/characters/{gateway.encoded(checkpoint['character_id'])}/hermes/export")
    after = owner_file.read_text(encoding="utf-8")
    if checkpoint["candidate_id"] not in imported.get("imported_candidate_ids", []):
        raise RuntimeError("candidate identity changed across restart")
    if exported.get("exported_memory_ids") != [checkpoint["native_memory_id"]]:
        raise RuntimeError("export selection changed across restart")
    if before != after or _hash(after) != checkpoint["file_sha256"]:
        raise RuntimeError("Character Hermes file changed across restart")

    for session_key, memory_key, revision_key in (
        ("maya_session_id", "native_memory_id", "native_memory_revision"),
        ("maya_session_id", "approved_memory_id", "approved_memory_revision"),
        ("alex_session_id", "alex_memory_id", "alex_memory_revision"),
    ):
        gateway.request(
            "DELETE",
            f"/api/assistant/memory/{gateway.encoded(checkpoint[memory_key])}?session_id={quote(checkpoint[session_key])}&expected_revision={checkpoint[revision_key]}",
        )
    gateway.request(
        "DELETE", f"/api/assistant/memory/candidates/{gateway.encoded(checkpoint['candidate_id'])}",
        payload={"session_id": checkpoint["maya_session_id"], "expected_status": "accepted"},
    )
    for key in ("maya_session_id", "alex_session_id"):
        gateway.request("DELETE", f"/api/chat/sessions/{gateway.encoded(checkpoint[key])}")
    owner_file.unlink()
    owner_file.parent.rmdir()
    Path(checkpoint["hermes_root"]).rmdir()

    report = {
        "format_version": "character-stage6-live-report-v1", "mode": "verify-restart",
        "decision": "pass", "generated_at": _now(),
        "checks": {
            "candidate_identity_persisted": True, "export_selection_persisted": True,
            "file_byte_identical": True, "feedback_loop_blocked": True,
            "fixture_records_deleted": 3, "fixture_candidates_deleted": 1,
            "fixture_sessions_deleted": 2, "isolated_hermes_directory_deleted": True,
        },
        "file_sha256": _hash(after),
    }
    _write(Path(args.report), report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the live Character Mode Stage 6 Hermes rehearsal.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    prepare_parser.add_argument("--hermes-root", default="resources/data/test-results/character-mode-stage6-hermes")
    prepare_parser.add_argument("--character-id", default="stage6-maya")
    prepare_parser.add_argument("--control-character-id", default="stage6-alex")
    prepare_parser.add_argument("--timeout-seconds", type=float, default=120)
    prepare_parser.add_argument("--checkpoint", default="resources/data/test-results/character-mode-stage6-checkpoint.json")
    prepare_parser.add_argument("--report", default="resources/data/test-results/character-mode-stage6-prepare-report.json")
    verify_parser = commands.add_parser("verify-restart")
    verify_parser.add_argument("--base-url")
    verify_parser.add_argument("--timeout-seconds", type=float, default=120)
    verify_parser.add_argument("--checkpoint", default="resources/data/test-results/character-mode-stage6-checkpoint.json")
    verify_parser.add_argument("--report", default="resources/data/test-results/character-mode-stage6-final-report.json")
    args = parser.parse_args(argv)
    try:
        report = prepare(args) if args.command == "prepare" else verify(args)
    except Exception as exc:
        report = {
            "format_version": "character-stage6-live-report-v1", "mode": args.command,
            "decision": "blocked", "generated_at": _now(), "error": f"{type(exc).__name__}: {exc}"[:500],
        }
        _write(Path(args.report), report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["decision"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
