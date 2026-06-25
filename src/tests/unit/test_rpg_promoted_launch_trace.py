"""Regression coverage for promoted RPG new-game server tracing."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_promoted_launch_trace_event_shape():
    from app.rpg.session.genesis.promoted_launch import _record_trace_event
    import time

    started_at = time.perf_counter()
    events = []
    _record_trace_event(events, "compile_genesis", "completed", started_at)

    assert len(events) == 1
    assert events[0]["stage"] == "compile_genesis"
    assert events[0]["status"] == "completed"
    assert isinstance(events[0]["elapsed_ms"], int)
