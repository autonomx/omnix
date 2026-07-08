from __future__ import annotations

import json

from scripts.chat_memory_stage1_preflight import run_preflight

NOW = "2026-07-08T00:00:00+00:00"


def _legacy_payload():
    return {
        "sessions": [
            {
                "id": "chat:stage1",
                "title": "Stage 1 rehearsal",
                "message_count": 2,
                "created_at": NOW,
                "updated_at": NOW,
                "messages": [
                    {
                        "id": "msg:one",
                        "role": "user",
                        "content": "Hello",
                        "created_at": NOW,
                        "metadata": {},
                    },
                    {
                        "id": "msg:two",
                        "role": "assistant",
                        "content": "Hi",
                        "created_at": NOW,
                        "metadata": {},
                    },
                ],
            }
        ]
    }


def test_stage1_preflight_rehearses_json_import_without_target_db_mutation(tmp_path, monkeypatch):
    legacy = tmp_path / "omnix_chat_sessions.json"
    target_db = tmp_path / "production-chat.sqlite3"
    legacy.write_text(json.dumps(_legacy_payload()), encoding="utf-8")
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(legacy))
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_DB_PATH", str(target_db))
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_SUGGESTIONS_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "0")
    monkeypatch.setenv("OMNIX_CHAT_COMPACTION_ENABLED", "0")
    monkeypatch.setenv("OMNIX_HERMES_MEMORY_SYNC_ENABLED", "0")

    report = run_preflight()

    assert report["ok"] is True
    assert report["legacy_json"]["sessions_in_json"] == 1
    assert report["legacy_json"]["messages_in_json"] == 2
    assert report["target_sqlite_db"] == str(target_db)
    assert report["rehearsal"]["sessions_after_import"] == 1
    assert report["rehearsal"]["messages_after_import"] == 2
    assert report["rehearsal"]["import_state"]["status"] == "completed"
    assert not target_db.exists()


def test_stage1_preflight_reports_warnings_for_non_stage1_flags(tmp_path, monkeypatch):
    legacy = tmp_path / "missing.json"
    monkeypatch.setenv("OMNIX_CHAT_STORE_PATH", str(legacy))
    monkeypatch.setenv("OMNIX_CHAT_SQLITE_DB_PATH", str(tmp_path / "chat.sqlite3"))
    monkeypatch.setenv("OMNIX_CHAT_MEMORY_ENABLED", "1")
    monkeypatch.setenv("OMNIX_CHAT_HISTORY_RECALL_ENABLED", "true")

    report = run_preflight()

    assert report["ok"] is True
    assert "curated memory is enabled; Stage 1 should keep it disabled" in report["warnings"]
    assert "OMNIX_CHAT_HISTORY_RECALL_ENABLED is enabled; Stage 1 should keep this disabled" in report["warnings"]
