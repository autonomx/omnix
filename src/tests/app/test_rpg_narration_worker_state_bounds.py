from app.apps.rpg.session import narration_worker


def test_pending_narration_signals_expire_and_reject_over_capacity(monkeypatch) -> None:
    narration_worker.clear_pending_session_signals()
    monkeypatch.setattr(narration_worker, "MAX_PENDING_SESSION_SIGNALS", 2)
    monkeypatch.setattr(narration_worker, "PENDING_SESSION_SIGNAL_TTL_SECONDS", 5.0)
    now = {"value": 10.0}
    monkeypatch.setattr(narration_worker.time, "monotonic", lambda: now["value"])

    assert narration_worker.signal_narration_work("first") is True
    assert narration_worker.signal_narration_work("second") is True
    assert narration_worker.signal_narration_work("third") is False
    assert narration_worker.drain_pending_sessions() == ["first", "second"]

    narration_worker.signal_narration_work("expired")
    now["value"] = 16.0
    assert narration_worker.drain_pending_sessions() == []
    narration_worker.clear_pending_session_signals()


def test_narration_worker_processes_pending_sessions_in_preserved_batches(monkeypatch) -> None:
    narration_worker.clear_pending_session_signals()
    monkeypatch.setattr(narration_worker, "_MAX_SESSIONS_PER_WAKE", 2)
    for session_id in ("one", "two", "three"):
        narration_worker.signal_narration_work(session_id)

    assert narration_worker.drain_pending_sessions() == ["one", "two"]
    assert narration_worker.drain_pending_sessions() == ["three"]
    narration_worker.clear_pending_session_signals()
