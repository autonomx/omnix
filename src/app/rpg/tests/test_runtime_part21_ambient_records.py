from app.rpg.session import runtime_part21


def test_ambient_interrupt_reinitializes_llm_records_after_session_swap(monkeypatch):
    monkeypatch.setattr(
        runtime_part21,
        "narrate_ambient_update",
        lambda **kwargs: {
            "text": "Bran warns you from across the room.",
            "speaker_turns": [],
            "used_app_llm": False,
            "raw_llm_narrative": "",
            "structured": {},
        },
    )
    monkeypatch.setattr(
        runtime_part21,
        "classify_ambient_delivery",
        lambda session, update, is_typing=False: "interrupt",
    )

    def record_interrupt_without_record_state(session, update):
        updated = dict(session)
        runtime_state = dict(updated.get("runtime_state") or {})
        runtime_state.pop("llm_records", None)
        runtime_state.pop("llm_records_index", None)
        runtime_state["pending_interrupt"] = {"ambient_id": update["ambient_id"]}
        updated["runtime_state"] = runtime_state
        return updated

    monkeypatch.setattr(
        runtime_part21,
        "record_interrupt",
        record_interrupt_without_record_state,
    )

    updates = [
        {
            "seq": 1,
            "ambient_id": "ambient:test",
            "kind": "warning",
            "text": "Bran warns you.",
            "priority": 1.0,
            "speaker_id": "npc:bran",
            "speaker_name": "Bran",
        }
    ]

    narrated_updates, runtime_state = runtime_part21._apply_ambient_narration_and_delivery(
        session={"runtime_state": {"tick": 1}},
        updates=updates,
        after_state={},
        runtime_state={"tick": 1, "current_scene": {}},
        idle_capture_key="idle:1",
    )

    assert narrated_updates[0]["delivery"] == "interrupt"
    assert len(runtime_state["llm_records"]) == 1
    assert runtime_state["llm_records"][0]["type"] == "ambient_narration"
    assert runtime_state["llm_records_index"]["idle:1:ambient:0"]["ambient_id"] == "ambient:test"
