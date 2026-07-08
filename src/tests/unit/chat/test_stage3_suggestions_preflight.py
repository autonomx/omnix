from __future__ import annotations

from scripts.chat_memory_stage3_preflight import run_preflight


def test_stage3_preflight_validates_pending_suggestion_lifecycle(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    rehearsal = report["rehearsal"]
    assert rehearsal["job_id"] == rehearsal["retry_job_id"]
    assert rehearsal["candidate_ids_first_process"] == rehearsal["candidate_ids_second_process"]
    assert rehearsal["pending_candidate_count"] == 1
    assert rehearsal["candidate_source"] == "assistant_suggested"
    assert rehearsal["candidate_status"] == "pending"
    assert rehearsal["candidate_trust_level"] == "unverified_agent"
    assert rehearsal["active_selected_count_before_approval"] == 0
    assert rehearsal["snapshot_count_before_approval"] == 0
    assert rehearsal["snapshot_count_immediately_after_approval"] == 0
    assert rehearsal["snapshot_count_after_refresh"] == 1
    assert rehearsal["external_candidate_ids"] == []
    assert "external_or_instructional_content" in rehearsal["external_skipped_reasons"]
    assert rehearsal["pending_candidate_count_after_external"] == 0


def test_stage3_preflight_reports_warnings_for_out_of_stage_flags(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "true")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "yes")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "on")

    report = run_preflight()

    assert report["ok"] is True
    assert "SQLite Chat storage is not currently enabled; Stage 3 assumes Stage 1 is complete" in report["warnings"]
    assert "curated memory is not currently enabled; Stage 3 assumes Stage 2 is complete" in report["warnings"]
    assert "history recall is enabled; Stage 3 should keep it disabled" in report["warnings"]
    assert "compaction is enabled; Stage 3 should keep it disabled" in report["warnings"]
    assert "Hermes sync is enabled; Stage 3 should keep it disabled" in report["warnings"]
