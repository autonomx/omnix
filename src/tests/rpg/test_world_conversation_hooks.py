"""The world conversation tick calls narration and the session only through its hooks (R-3)."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.session.conversation_hooks import SESSION_CONVERSATION_HOOKS
from app.apps.rpg.world.contracts import ConversationHooks
from app.apps.rpg.world.social.conversation_engine import build_next_conversation_line, run_conversation_tick

CONVERSATION = {"conversation_id": "conv-1", "participants": ["npc_a", "npc_b"], "turn_count": 0}


def _states(*, llm: bool, mode: str = "live") -> tuple[dict[str, Any], dict[str, Any]]:
    simulation_state: dict[str, Any] = {"conversation_settings": {"llm_expand_npc_conversations": llm}}
    return simulation_state, {"mode": mode}


def test_a_live_line_is_written_by_the_hook_and_recorded_for_replay() -> None:
    calls = []

    def write_line(conversation, speaker_id, simulation_state, runtime_state, recent_lines):
        calls.append(speaker_id)
        return {"parsed": {"speaker": speaker_id, "text": "The road north is closed.", "kind": "statement"}}

    simulation_state, runtime_state = _states(llm=True)
    line = build_next_conversation_line(dict(CONVERSATION), simulation_state, runtime_state, 7, write_line)

    assert calls == ["npc_a"]
    assert line["source"] == "llm"
    assert line["text"] == "The road north is closed."
    assert runtime_state["llm_records_index"] == {"conversation_line:conv-1:1": 0}

    # Replay reads the recorded line back without any writer.
    replay_state = {**runtime_state, "mode": "replay"}
    replayed = build_next_conversation_line(dict(CONVERSATION), simulation_state, replay_state, 7)
    assert replayed["source"] == "llm"
    assert replayed["text"] == "The road north is closed."


def test_without_a_writer_or_the_setting_the_line_comes_from_a_template() -> None:
    def write_line(*args):
        raise AssertionError("the setting is off")

    for llm, writer in ((True, None), (False, write_line)):
        simulation_state, runtime_state = _states(llm=llm)
        line = build_next_conversation_line(dict(CONVERSATION), simulation_state, runtime_state, 7, writer)
        assert line["source"] == "template"


def test_the_tick_reports_to_the_session_hook_and_survives_its_failure() -> None:
    seen = []

    def after_tick(session_id, simulation_state, runtime_state):
        seen.append(session_id)
        return {"runtime_state": {**runtime_state, "ambient_queued": True}}

    runtime_state: dict[str, Any] = {"session_id": "session-1"}
    run_conversation_tick({}, runtime_state, 3, ConversationHooks(after_tick=after_tick))
    assert seen == ["session-1"]
    assert runtime_state["ambient_queued"] is True

    def failing(*args):
        raise RuntimeError("narration queue down")

    run_conversation_tick({}, {"session_id": "session-1"}, 4, ConversationHooks(after_tick=failing))


def test_the_session_supplies_narration_and_ambient_queueing() -> None:
    assert SESSION_CONVERSATION_HOOKS.write_line is not None
    assert SESSION_CONVERSATION_HOOKS.after_tick is not None
