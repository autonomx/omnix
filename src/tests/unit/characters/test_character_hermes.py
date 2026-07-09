from __future__ import annotations

from pathlib import Path

from app.assistant_memory import resolve_chat_scope
from app.assistant_memory.hermes_adapter import (
    export_approved_memory_to_hermes,
    import_hermes_memory,
)
from app.assistant_memory.owner_repository import OwnerAwareSQLiteMemoryRepository
from app.assistant_memory.owner_service import OwnerAwareMemoryService
from app.characters.hermes_adapter import (
    export_character_memory_to_hermes,
    import_character_hermes_memory,
)


def _service(tmp_path: Path) -> OwnerAwareMemoryService:
    return OwnerAwareMemoryService(
        OwnerAwareSQLiteMemoryRepository(tmp_path / "memory.sqlite3")
    )


def _context(character_id: str):
    return resolve_chat_scope(
        f"character-hermes:{character_id}",
        owner_type="character",
        owner_id=character_id,
    )


def test_character_sync_is_disabled_by_default_and_missing_storage_is_non_fatal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path)
    context = _context("maya")
    root = tmp_path / "character-hermes"
    monkeypatch.delenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", raising=False)

    disabled = import_character_hermes_memory(
        service,
        context,
        "maya",
        memory_dir=root,
    )
    assert disabled.enabled is False
    assert disabled.skipped_reasons == ["character_sync_disabled"]

    monkeypatch.setenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", "1")
    missing = import_character_hermes_memory(
        service,
        context,
        "maya",
        memory_dir=root,
    )
    assert missing.enabled is True
    assert missing.available is False
    assert missing.skipped_reasons == ["character_hermes_directory_missing"]
    assert service.list_active(context) == []


def test_character_import_is_review_first_idempotent_and_owner_bound(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path)
    maya = _context("maya")
    root = tmp_path / "character-hermes"
    maya_root = root / "maya"
    maya_root.mkdir(parents=True)
    (maya_root / "CHARACTER.md").write_text(
        "# Maya notes\n"
        "- The user likes rainy hikes\n"
        "- API key is hidden\n"
        "<!-- OMNIX CHARACTER maya MANAGED MEMORY BEGIN -->\n"
        "- Previously exported memory\n"
        "<!-- OMNIX CHARACTER maya MANAGED MEMORY END -->\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", "1")

    first = import_character_hermes_memory(
        service,
        maya,
        "maya",
        memory_dir=root,
    )
    second = import_character_hermes_memory(
        service,
        maya,
        "maya",
        memory_dir=root,
    )

    assert second.imported_candidate_ids == first.imported_candidate_ids
    candidates = service.owner_repository.list_candidates(
        owner_type="character",
        owner_id="maya",
        status="pending",
    )
    assert len(candidates) == 1
    assert candidates[0].proposed_content == "The user likes rainy hikes"
    assert candidates[0].source == "hermes"
    assert candidates[0].extraction_metadata["review_required"] is True
    assert service.list_active(maya) == []

    mismatch = import_character_hermes_memory(
        service,
        maya,
        "alex",
        memory_dir=root,
    )
    assert mismatch.skipped_reasons == ["character_owner_mismatch"]


def test_character_export_excludes_other_owners_session_records_and_feedback_loops(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path)
    maya = _context("maya")
    alex = _context("alex")
    system = resolve_chat_scope("chat:system")
    root = tmp_path / "character-hermes"
    maya_record = service.create_explicit_memory(
        maya,
        scope="global",
        category="relationship",
        content="Maya and the user share a rainy hike joke.",
        provenance_id="message:maya",
    )
    service.create_explicit_memory(
        maya,
        scope="session",
        category="fact",
        content="Temporary call detail.",
        provenance_id="message:temporary",
    )
    service.create_explicit_memory(
        alex,
        scope="global",
        category="relationship",
        content="Alex-only relationship memory.",
        provenance_id="message:alex",
    )
    service.create_explicit_memory(
        system,
        scope="global",
        category="preference",
        content="System Assistant preference.",
        provenance_id="message:system",
    )
    candidate = service.propose_memory(
        maya,
        source_session_id=maya.session_id,
        source_message_id="character-hermes:maya:imported",
        scope="global",
        category="relationship",
        content="Imported Hermes memory.",
        confidence=0.7,
        source="hermes",
    )
    service.approve_candidate(maya, candidate.id)
    monkeypatch.setenv("OMNIX_CHARACTER_HERMES_SYNC_ENABLED", "1")

    status = export_character_memory_to_hermes(
        service,
        maya,
        "maya",
        memory_dir=root,
    )
    text = (root / "maya" / "CHARACTER.md").read_text(encoding="utf-8")

    assert status.exported_memory_ids == [maya_record.id]
    assert maya_record.content in text
    assert "Temporary call detail" not in text
    assert "Alex-only" not in text
    assert "System Assistant preference" not in text
    assert "Imported Hermes memory" not in text


def test_ordinary_hermes_adapter_rejects_character_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = _service(tmp_path)
    maya = _context("maya")
    root = tmp_path / "ordinary-hermes"
    root.mkdir()
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "1")

    imported = import_hermes_memory(service, maya, memory_dir=root)
    exported = export_approved_memory_to_hermes(service, maya, memory_dir=root)

    assert imported.skipped_reasons == ["system_owner_required"]
    assert exported.skipped_reasons == ["system_owner_required"]
    assert not (root / "USER.md").exists()
    assert not (root / "MEMORY.md").exists()
