from __future__ import annotations

from app.rpg.autoplay_verification_gate import build_autoplay_verification_gate


def test_phase26_gate_flags_missing_summary() -> None:
    report = build_autoplay_verification_gate({"completed_turns": 1, "transcript_rows": [{}]})

    assert report["ready"] is False
    assert "turn_target_not_met" in report["issues"]
    assert "missing_summary_report_surface" in report["issues"]
