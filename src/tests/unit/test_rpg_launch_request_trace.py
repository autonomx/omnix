"""Regression tests for RPG campaign creation request trace shape."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_campaign_creation_progress_contract_remains_completed_without_background_job():
    from app.rpg.session.new_game_creation_progress import build_creation_job, build_creation_progress_snapshot

    job = build_creation_job(session_id="rpg_trace_test", status="completed", timestamp="2026-06-25T00:00:00Z")
    progress = build_creation_progress_snapshot(session_id="rpg_trace_test", status="completed")

    assert job["type"] == "rpg.new_game.create"
    assert job["status"] == "completed"
    assert progress["progress"] == 100
    assert progress["stage"] == "ready_first_turn"
