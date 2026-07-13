#!/usr/bin/env python3
"""Temporary in-memory preflight for optional Character Hermes compatibility."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.assistant_memory import (  # noqa: E402
    OwnerAwareInMemoryMemoryRepository,
    OwnerAwareMemoryService,
    resolve_chat_scope,
)
from app.characters.hermes_adapter import (  # noqa: E402
    export_character_memory_to_hermes,
    import_character_hermes_memory,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@contextmanager
def _sync_flag(value: str) -> Iterator[None]:
    name = "OMNIX_CHARACTER_HERMES_SYNC_ENABLED"
    previous = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def run_preflight() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    def check(check_id: str, operation) -> Any:
        try:
            value, observed = operation()
            checks.append({"id": check_id, "status": "pass", "observed": observed})
            return value
        except Exception as exc:
            checks.append({"id": check_id, "status": "fail", "error": f"{type(exc).__name__}: {exc}"[:500]})
            errors.append(check_id)
            return None

    with tempfile.TemporaryDirectory(prefix="omnix-character-stage6-") as raw:
        temp = Path(raw)
        service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(temp / "memory"))
        maya = resolve_chat_scope("character-hermes:stage6-maya", owner_type="character", owner_id="stage6-maya")
        alex = resolve_chat_scope("character-hermes:stage6-alex", owner_type="character", owner_id="stage6-alex")
        system = resolve_chat_scope("character-hermes:system")

        def disabled_check():
            with _sync_flag("0"):
                result = import_character_hermes_memory(service, maya, "stage6-maya", memory_dir=temp / "disabled")
            if result.enabled or result.imported_candidate_ids:
                raise RuntimeError("disabled synchronization imported data")
            return result, {"enabled": result.enabled, "candidate_count": 0, "reasons": result.skipped_reasons}

        check("sync.disabled", disabled_check)

        def missing_check():
            with _sync_flag("1"):
                result = import_character_hermes_memory(service, maya, "stage6-maya", memory_dir=temp / "missing")
            if result.available or result.skipped_reasons != ["character_hermes_directory_missing"]:
                raise RuntimeError("missing storage was not nonfatal")
            return result, {"available": result.available, "reasons": result.skipped_reasons}

        check("storage.missing_nonfatal", missing_check)

        import_root = temp / "import"
        owner_root = import_root / "stage6-maya"
        owner_root.mkdir(parents=True)
        unmanaged = "The user prefers carefully reviewed character memories."
        blocked = "API key is a synthetic blocked value."
        managed = "Previously managed export must not return."
        (owner_root / "CHARACTER.md").write_text(
            "# Character notes\n"
            f"- {unmanaged}\n"
            f"- {blocked}\n"
            "<!-- OMNIX CHARACTER stage6-maya MANAGED MEMORY BEGIN -->\n"
            f"- {managed}\n"
            "<!-- OMNIX CHARACTER stage6-maya MANAGED MEMORY END -->\n",
            encoding="utf-8",
        )

        def import_check():
            with _sync_flag("1"):
                first = import_character_hermes_memory(service, maya, "stage6-maya", memory_dir=import_root)
                second = import_character_hermes_memory(service, maya, "stage6-maya", memory_dir=import_root)
            candidates = service.owner_repository.list_candidates(owner_type="character", owner_id="stage6-maya", status="pending")
            if len(candidates) != 1 or first.imported_candidate_ids != second.imported_candidate_ids:
                raise RuntimeError("character import was not review-first and idempotent")
            if candidates[0].proposed_content != unmanaged or candidates[0].source != "hermes":
                raise RuntimeError("character import screening selected the wrong content")
            if service.list_active(maya):
                raise RuntimeError("pending import became active memory")
            return candidates[0], {
                "candidate_count": len(candidates),
                "candidate_ids_stable": first.imported_candidate_ids == second.imported_candidate_ids,
                "candidate_content_sha256": _sha256(candidates[0].proposed_content),
                "source": candidates[0].source,
                "active_record_count": 0,
            }

        candidate = check("import.review_first_idempotent", import_check)

        def owner_check():
            with _sync_flag("1"):
                mismatch = import_character_hermes_memory(service, maya, "stage6-alex", memory_dir=import_root)
                system_result = import_character_hermes_memory(service, system, "stage6-maya", memory_dir=import_root)
            expected = ["character_owner_mismatch"], ["character_owner_required"]
            if (mismatch.skipped_reasons, system_result.skipped_reasons) != expected:
                raise RuntimeError("owner binding did not reject mismatched contexts")
            return True, {"mismatch_reasons": mismatch.skipped_reasons, "system_reasons": system_result.skipped_reasons}

        check("owner.binding", owner_check)

        export_root = temp / "export"
        export_owner = export_root / "stage6-maya"
        export_owner.mkdir(parents=True)
        preserved = "Keep this unmanaged character note."
        (export_owner / "CHARACTER.md").write_text(f"# Existing notes\n{preserved}\n", encoding="utf-8")

        compatible = service.create_explicit_memory(
            maya, scope="global", category="relationship",
            content="Synthetic approved Stage 6 relationship.", provenance_id="stage6:compatible",
        )
        service.create_explicit_memory(
            maya, scope="session", category="fact",
            content="Synthetic session-only Stage 6 detail.", provenance_id="stage6:session",
        )
        service.create_explicit_memory(
            alex, scope="global", category="relationship",
            content="Synthetic Alex-only Stage 6 relationship.", provenance_id="stage6:alex",
        )
        service.create_explicit_memory(
            system, scope="global", category="preference",
            content="Synthetic System Assistant Stage 6 preference.", provenance_id="stage6:system",
        )
        if candidate is not None:
            service.approve_candidate(maya, candidate.id)

        def export_check():
            with _sync_flag("1"):
                first = export_character_memory_to_hermes(service, maya, "stage6-maya", memory_dir=export_root)
                first_text = (export_owner / "CHARACTER.md").read_text(encoding="utf-8")
                second = export_character_memory_to_hermes(service, maya, "stage6-maya", memory_dir=export_root)
                second_text = (export_owner / "CHARACTER.md").read_text(encoding="utf-8")
            if first.exported_memory_ids != [compatible.id] or second.exported_memory_ids != first.exported_memory_ids:
                raise RuntimeError("export selected incompatible records")
            if first_text != second_text or preserved not in second_text:
                raise RuntimeError("export was not idempotent or removed unmanaged text")
            if second_text.count("OMNIX CHARACTER stage6-maya MANAGED MEMORY BEGIN") != 1:
                raise RuntimeError("export created duplicate managed blocks")
            return second_text, {
                "exported_memory_ids": second.exported_memory_ids,
                "exported_count": len(second.exported_memory_ids),
                "byte_identical": first_text == second_text,
                "unmanaged_preserved": preserved in second_text,
                "managed_block_count": 1,
                "file_sha256": _sha256(second_text),
            }

        exported_text = check("export.filtered_idempotent", export_check)

        def rollback_check():
            before = (export_owner / "CHARACTER.md").read_text(encoding="utf-8")
            active_before = {record.id for record in service.list_active(maya)}
            with _sync_flag("0"):
                imported = import_character_hermes_memory(service, maya, "stage6-maya", memory_dir=import_root)
                exported = export_character_memory_to_hermes(service, maya, "stage6-maya", memory_dir=export_root)
            after = (export_owner / "CHARACTER.md").read_text(encoding="utf-8")
            active_after = {record.id for record in service.list_active(maya)}
            if imported.enabled or exported.enabled or before != after or active_before != active_after:
                raise RuntimeError("disabled adapter changed native memory or Hermes files")
            return True, {
                "import_enabled": imported.enabled,
                "export_enabled": exported.enabled,
                "file_unchanged": before == after,
                "native_memory_unchanged": active_before == active_after,
                "file_sha256": _sha256(after),
            }

        if exported_text is not None:
            check("rollback.non_destructive", rollback_check)

    return {
        "format_version": "character-stage6-preflight-v1",
        "decision": "pass" if not errors else "blocked",
        "checks": checks,
        "notes": [
            "Temporary files and in-memory state are deleted after the preflight.",
            "The report contains IDs, hashes, counts, statuses, and reasons only.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Character Mode Stage 6 Hermes preflight.")
    parser.add_argument("--report", default="resources/data/test-results/character-mode-stage6-preflight-report.json")
    args = parser.parse_args(argv)
    report = run_preflight()
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["decision"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
