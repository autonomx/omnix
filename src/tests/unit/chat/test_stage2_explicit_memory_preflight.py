from __future__ import annotations

from scripts.chat_memory_stage2_preflight import run_preflight


def test_stage2_preflight_validates_explicit_memory_snapshot_and_forget(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    rehearsal = report["rehearsal"]
    assert rehearsal["snapshot_revision"] == 1
    assert rehearsal["snapshot_record_count"] == 1
    assert len(rehearsal["selected_memory_ids"]) == 1
    assert rehearsal["pending_candidate_count"] == 0
    assert rehearsal["memory_present_in_prompt"] is True
    assert rehearsal["memory_present_after_forget"] is False
    assert rehearsal["selected_count_after_forget"] == 0
    assert report["original_flags"]["OMNIX_CHAT_MEMORY_ENABLED"]["enabled"] is False


def test_stage2_preflight_reports_warnings_for_out_of_stage_flags(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "true")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "yes")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "on")

    report = run_preflight()

    assert report["ok"] is True
    assert "SQLite Chat storage is not currently enabled; Stage 2 assumes Stage 1 is complete" in report["warnings"]
    assert "suggestions are enabled; Stage 2 should keep them disabled" in report["warnings"]
    assert "history recall is enabled; Stage 2 should keep it disabled" in report["warnings"]
    assert "compaction is enabled; Stage 2 should keep it disabled" in report["warnings"]
    assert "Hermes sync is enabled; Stage 2 should keep it disabled" in report["warnings"]
