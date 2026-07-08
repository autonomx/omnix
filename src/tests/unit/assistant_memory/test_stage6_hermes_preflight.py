from __future__ import annotations

from scripts.chat_memory_stage6_preflight import run_preflight


def test_stage6_preflight_validates_review_first_hermes_sync(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "1")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    rehearsal = report["rehearsal"]
    assert rehearsal["disabled_initial"]["enabled"] is False
    assert rehearsal["disabled_initial"]["imported_candidate_ids"] == []
    assert rehearsal["missing_status"]["enabled"] is True
    assert rehearsal["missing_status"]["available"] is False
    assert rehearsal["missing_status"]["skipped_reasons"] == [
        "hermes_memory_directory_missing"
    ]
    assert rehearsal["candidate_contents_after_first"] == [
        "Prefers concise release reports",
        "The rpg branch is authoritative",
    ]
    assert rehearsal["candidate_contents_after_second"] == [
        "Prefers concise release reports",
        "The rpg branch is authoritative",
    ]
    assert rehearsal["pending_candidate_count_after_first"] == 2
    assert rehearsal["pending_candidate_count_after_second"] == 2
    assert rehearsal["active_count_before_approval"] == 0
    assert rehearsal["approved_hermes_record_source"] == "hermes"
    assert set(rehearsal["first_export"]["exported_memory_ids"]) == set(
        rehearsal["expected_export_ids"]
    )
    assert rehearsal["first_export"]["exported_memory_ids"] == rehearsal[
        "second_export"
    ]["exported_memory_ids"]
    assert rehearsal["exports_are_byte_identical"] is True
    assert rehearsal["unmanaged_user_text_preserved"] is True
    assert rehearsal["unmanaged_project_text_preserved"] is True
    assert rehearsal["managed_user_block_count"] == 1
    assert rehearsal["managed_project_block_count"] == 1
    assert rehearsal["personal_export_count"] == 1
    assert rehearsal["project_export_count"] == 1
    assert rehearsal["hermes_record_exported"] is False
    assert rehearsal["session_record_exported"] is False
    assert rehearsal["pending_candidate_exported"] is False
    assert rehearsal["unavailable_export"]["available"] is False
    assert rehearsal["unavailable_export"]["skipped_reasons"][0].startswith(
        "hermes_write_failed:"
    )
    assert rehearsal["disabled_import"]["enabled"] is False
    assert rehearsal["disabled_export"]["enabled"] is False
    assert rehearsal["rollback_files_unchanged"] is True
    assert rehearsal["native_memory_unchanged_after_rollback"] is True


def test_stage6_preflight_reports_missing_prerequisite_warnings(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    assert len(report["warnings"]) == 5
    assert any("Stage 1 SQLite Chat storage" in item for item in report["warnings"])
    assert any("Stage 2 curated memory" in item for item in report["warnings"])
    assert any("Stage 3 pending suggestions" in item for item in report["warnings"])
    assert any("Stage 4 history recall" in item for item in report["warnings"])
    assert any("Stage 5 compaction" in item for item in report["warnings"])
