from __future__ import annotations

from scripts.chat_memory_stage5_preflight import run_preflight


def test_stage5_preflight_validates_safe_long_session_compaction(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    rehearsal = report["rehearsal"]
    assert rehearsal["below_threshold_job_created"] is False
    assert rehearsal["job_id"] == rehearsal["retry_job_id"]
    assert rehearsal["job_type"] == "assistant.history.compact"
    assert rehearsal["job_count"] == 1
    assert (
        rehearsal["job_through_message_id"]
        == rehearsal["expected_through_message_id"]
    )
    assert rehearsal["pending_summary_id"] is None
    assert rehearsal["pending_recent_message_count"] == 60
    assert rehearsal["pending_prompt_has_oldest_message"] is True
    assert rehearsal["summary_revision"] == 1
    assert (
        rehearsal["summary_through_message_id"]
        == rehearsal["expected_through_message_id"]
    )
    assert rehearsal["summary_source_message_count"] == 36
    assert rehearsal["summary_has_durable_decisions"] is True
    assert rehearsal["summary_has_unresolved_items"] is True
    assert rehearsal["latest_summary_id"] == rehearsal["summary_id"]
    assert rehearsal["completed_job_status"] == "completed"
    assert rehearsal["completed_job_output_refs"] == [
        {"type": "conversation_summary", "id": rehearsal["summary_id"]}
    ]
    assert rehearsal["compacted_summary_id"] == rehearsal["summary_id"]
    assert rehearsal["compacted_recent_message_count"] == 24
    assert (
        rehearsal["compacted_first_recent_message_id"]
        == rehearsal["expected_first_recent_message_id"]
    )
    assert rehearsal["compacted_prompt_has_summary"] is True
    assert rehearsal["compacted_prompt_has_recent_tail"] is True
    assert rehearsal["compacted_prompt_has_oldest_message"] is False
    assert rehearsal["disabled_compaction_diagnostics"] == {
        "enabled": False,
        "summary_id": None,
    }
    assert rehearsal["disabled_recent_message_count"] == 60
    assert rehearsal["disabled_prompt_has_summary"] is False
    assert rehearsal["disabled_prompt_has_oldest_message"] is True


def test_stage5_preflight_reports_out_of_stage_warnings(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "true")

    report = run_preflight()

    assert report["ok"] is True
    assert (
        "SQLite Chat storage is not currently enabled; Stage 5 assumes Stage 1 is complete"
        in report["warnings"]
    )
    assert (
        "curated memory is not currently enabled; Stage 5 assumes Stage 2 is complete"
        in report["warnings"]
    )
    assert (
        "memory suggestions are not currently enabled; Stage 5 assumes Stage 3 is complete"
        in report["warnings"]
    )
    assert (
        "history recall is not currently enabled; Stage 5 assumes Stage 4 is complete"
        in report["warnings"]
    )
    assert "Hermes sync is enabled; Stage 5 should keep it disabled" in report["warnings"]
