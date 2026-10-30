"""The live portrait's paired release gate (roadmap Phase 5)."""
from __future__ import annotations

import json

from app.platform.live_voice.portrait_gate import PortraitGateThresholds, evaluate_portrait_pairing
from app.platform.live_voice.release_gate_cli import main

SCENARIOS = ("character-normal", "hard-stop")


def _run(portrait: bool, *, latency: float, tokens: float, underruns: int = 0, replies: int = 3) -> list[dict]:
    events = []
    for scenario in SCENARIOS:
        for reply in range(replies):
            base = {"event": "release_metric", "portrait": portrait, "scenario": scenario}
            for name in ("stt_finalize_ms", "final_to_first_token_ms", "first_token_to_first_audio_ms",
                         "final_to_first_playback_ms", "speech_end_to_first_playback_ms", "first_audible_ms",
                         "interruption_to_silence_ms"):
                events.append({**base, "metric_name": name, "value_ms": latency + reply})
            events.append({**base, "metric_name": "llm_tokens_per_second", "value_ms": tokens + reply})
            events.append({**base, "metric_name": "underrun_count", "value_ms": underruns})
            if portrait:
                events.append({**base, "metric_name": "start_hold_ms", "value_ms": 20.0 + reply})
                events.append({"event": "release_metric_batch", "portrait": True, "metric_name": "av_offset_ms",
                               "values": [-15.0, 4.0, 18.5]})
    return events


def _limits() -> PortraitGateThresholds:
    return PortraitGateThresholds(minimum_replies=3, minimum_interruptions=3, required_scenarios=SCENARIOS)


def test_a_portrait_that_costs_nothing_passes() -> None:
    report = evaluate_portrait_pairing(_run(False, latency=500, tokens=80) + _run(True, latency=520, tokens=78),
                                       _limits())
    assert report.status == "pass", [check for check in report.checks if check.status != "pass"]
    tokens = next(check for check in report.checks if check.name == "llm_tokens_per_second")
    assert tokens.interval is not None and tokens.interval[0] <= tokens.on / tokens.off <= tokens.interval[1]
    assert report.replies == {"off": {"character-normal": 3, "hard-stop": 3}, "on": {"character-normal": 3,
                                                                                     "hard-stop": 3}}


def test_slower_replies_more_underruns_or_a_long_hold_fail() -> None:
    events = _run(False, latency=500, tokens=80) + _run(True, latency=600, tokens=60, underruns=1)
    events.append({"event": "release_metric", "portrait": True, "metric_name": "start_hold_ms", "value_ms": 400.0,
                   "scenario": "hard-stop"})
    report = evaluate_portrait_pairing(events, _limits())
    failed = {check.name for check in report.checks if check.status == "fail"}
    assert report.status == "fail"
    assert {"first_audible_ms", "llm_tokens_per_second", "underrun_count"} <= failed
    assert "start_hold_ms" not in failed  # its p50 is still small


def test_too_few_replies_or_a_late_picture_are_reported() -> None:
    events = _run(False, latency=500, tokens=80, replies=1) + _run(True, latency=500, tokens=80)
    events.append({"event": "release_metric_batch", "portrait": True, "metric_name": "av_offset_ms",
                   "values": [90.0] * 50})
    events.append({"event": "release_counter", "portrait": True, "counter_name": "portrait_degrade_count"})
    report = evaluate_portrait_pairing(events, _limits())
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["replies:character-normal:off"] == "insufficient" and statuses["av_offset_ms"] == "fail"
    # An interruption scenario is counted by its interruptions, not its replies.
    assert statuses["interruptions:hard-stop:off"] == "insufficient" and "replies:hard-stop:off" not in statuses
    assert report.counters == {"portrait_degrade_count": 1}


def test_the_cli_compares_the_runs_in_the_live_call_log(tmp_path, capsys) -> None:
    log = tmp_path / "live-call-streaming.log"
    log.write_text("\n".join(json.dumps(event) for event in
                             _run(False, latency=500, tokens=80) + _run(True, latency=510, tokens=79)),
                   encoding="utf-8")
    code = main(["--log", str(log), "--portrait-pairing", "--minimum-replies", "3",
                 "--scenario", "character-normal"])
    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "pass"


def test_a_latency_a_few_milliseconds_slower_passes_whatever_its_ratio() -> None:
    # 18.7 ms against 14.2 ms is 132%, but 4.5 ms: below what a listener hears (owner decision 2026-10-30).
    events = []
    for portrait, value in ((False, 14.2), (True, 18.7)):
        for reply in range(3):
            events.append({"event": "release_metric", "portrait": portrait, "scenario": "hard-stop",
                           "metric_name": "interruption_to_silence_ms", "value_ms": value})
    report = evaluate_portrait_pairing(events, _limits())
    check = next(check for check in report.checks if check.name == "interruption_to_silence_ms")
    assert check.status == "pass" and "+20 ms" in check.detail
    slower = [dict(event, value_ms=event["value_ms"] + 30) if event["portrait"] else event for event in events]
    assert next(check for check in evaluate_portrait_pairing(slower, _limits()).checks
                if check.name == "interruption_to_silence_ms").status == "fail"

