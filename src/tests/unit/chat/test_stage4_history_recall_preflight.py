from __future__ import annotations

from scripts.chat_memory_stage4_preflight import run_preflight


def test_stage4_preflight_validates_scoped_history_recall(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    rehearsal = report["rehearsal"]
    assert rehearsal["history_status"]["available"] is True
    assert rehearsal["retrieved_session_ids"] == ["chat:same-scope"]
    assert rehearsal["retrieved_count"] <= 2
    assert rehearsal["prompt_history_diagnostics"]["enabled"] is True
    assert rehearsal["prompt_history_diagnostics"]["retrieved_count"] >= 1
    assert rehearsal["prompt_has_history_label"] is True
    assert rehearsal["prompt_has_same_scope_excerpt"] is True
    assert rehearsal["prompt_has_approved_memory_label"] is False
    assert rehearsal["deleted_match_count_before"] >= 1
    assert rehearsal["deleted_match_count_after"] == 0
    assert rehearsal["disabled_history_diagnostics"] == {
        "enabled": False,
        "retrieved_count": 0,
    }
    assert rehearsal["disabled_prompt_has_history_label"] is False
    assert rehearsal["degraded_history_diagnostics"]["status"]["available"] is False
    assert rehearsal["degraded_history_diagnostics"]["retrieved_count"] == 0
    assert rehearsal["degraded_prompt_has_history_label"] is False


def test_stage4_preflight_reports_out_of_stage_warnings(monkeypatch):
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_STORE_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "true")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "yes")

    report = run_preflight()

    assert report["ok"] is True
    assert (
        "SQLite Chat storage is not currently enabled; Stage 4 assumes Stage 1 is complete"
        in report["warnings"]
    )
    assert (
        "curated memory is not currently enabled; Stage 4 assumes Stage 2 is complete"
        in report["warnings"]
    )
    assert (
        "memory suggestions are not currently enabled; Stage 4 assumes Stage 3 is complete"
        in report["warnings"]
    )
    assert "compaction is enabled; Stage 4 should keep it disabled" in report["warnings"]
    assert "Hermes sync is enabled; Stage 4 should keep it disabled" in report["warnings"]
