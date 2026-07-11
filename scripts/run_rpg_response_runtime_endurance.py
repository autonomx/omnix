from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from app.rpg.session.runtime_part40 import apply_turn


_CATEGORIES = (
    "dialogue",
    "transaction",
    "travel",
    "combat",
    "companion",
    "investigation",
    "observation",
    "failure",
)


def _turn_fixture(turn: int) -> dict[str, Any]:
    category = _CATEGORIES[(turn - 1) % len(_CATEGORIES)]
    fixtures = {
        "dialogue": {
            "input": "Ask Bran what he knows about the eastern road.",
            "mode": "dialogue",
            "action_type": "social_activity",
            "narration": "Bran considers the question before answering.",
            "npc": {"speaker": "Bran", "line": "The eastern road is quiet today."},
            "allowed_speakers": ["Bran"],
        },
        "transaction": {
            "input": "Pay five silver for the room.",
            "mode": "transaction",
            "action_type": "service_purchase",
            "narration": "Bran accepts the payment and prepares the room.",
            "npc": {},
            "currency_delta": {"silver": -5},
            "inventory_delta": {"room_key": 1},
        },
        "travel": {
            "input": "Travel to the eastern gate.",
            "mode": "travel",
            "action_type": "travel",
            "narration": "You follow the resolved route to the eastern gate.",
            "npc": {},
            "current_location": "eastern_gate",
            "location_changed": True,
        },
        "combat": {
            "input": "Strike the practice dummy.",
            "mode": "combat",
            "action_type": "combat_attack",
            "narration": "Your strike lands on the practice dummy.",
            "npc": {},
            "combat_delta": {"practice_dummy_damage": 2},
        },
        "companion": {
            "input": "Ask Bran to keep watch.",
            "mode": "dialogue",
            "action_type": "companion_command",
            "narration": "Bran takes up a watchful position near the door.",
            "npc": {"speaker": "Bran", "line": "I will keep an eye on the room."},
            "allowed_speakers": ["Bran"],
        },
        "investigation": {
            "input": "Inspect the ledger for a matching name.",
            "mode": "investigation",
            "action_type": "investigation",
            "narration": "The visible ledger contains no matching entry.",
            "npc": {},
            "visible_facts": {"ledger_result": "No matching entry is visible."},
        },
        "observation": {
            "input": "Look around the tavern.",
            "mode": "observation",
            "action_type": "observation",
            "narration": "The tavern remains orderly and the exits are clear.",
            "npc": {},
        },
        "failure": {
            "input": "Open the sealed iron chest without a key.",
            "mode": "failure",
            "action_type": "failed_interaction",
            "narration": "The sealed chest does not open, but the lock can be inspected.",
            "npc": {},
            "mechanic_resolved": False,
            "resolver_status": "unresolved",
        },
    }
    return {"category": category, **fixtures[category]}


def _base_turn_factory(state: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    def _base(
        session_id: str,
        player_input: str,
        action: dict[str, Any] | None = None,
        *,
        performance_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        turn = int(state.get("turn_index") or 0) + 1
        fixture = _turn_fixture(turn)
        state["turn_index"] = turn
        state["tick"] = turn
        state["response_rollout_stage"] = "canonical_default"
        if fixture.get("current_location"):
            state["location_id"] = fixture["current_location"]
        resolved = {
            "ok": bool(fixture.get("mechanic_resolved", True)),
            "action_type": fixture["action_type"],
            "semantic_family": fixture["mode"],
            "response_mode": fixture["mode"],
            "summary": fixture["narration"],
            "mechanic_resolved": bool(fixture.get("mechanic_resolved", True)),
            "resolver_status": fixture.get("resolver_status", "resolved"),
            "allowed_speakers": list(fixture.get("allowed_speakers", ())),
            "currency_delta": deepcopy(fixture.get("currency_delta", {})),
            "inventory_delta": deepcopy(fixture.get("inventory_delta", {})),
            "combat_delta": deepcopy(fixture.get("combat_delta", {})),
            "current_location": fixture.get("current_location") or state.get("location_id"),
            "location_changed": bool(fixture.get("location_changed")),
            "visible_facts": deepcopy(fixture.get("visible_facts", {})),
        }
        contract = {
            "ok": True,
            "turn_id": f"endurance-turn-{turn}",
            "turn_index": turn,
            "action_type": fixture["action_type"],
            "semantic_family": fixture["mode"],
            "response_mode": fixture["mode"],
            "mechanic_resolved": resolved["mechanic_resolved"],
            "resolver_status": resolved["resolver_status"],
            "resolved_result": deepcopy(resolved),
            "simulation_state": deepcopy(state),
        }
        nested = {
            **deepcopy(resolved),
            "narration": fixture["narration"],
            "npc": deepcopy(fixture["npc"]),
            "simulation_state": deepcopy(state),
            "turn_contract": deepcopy(contract),
        }
        session = {
            "session_id": session_id,
            "simulation_state": deepcopy(state),
            "runtime_state": {
                "tick": turn,
                "performance": {
                    "enable_live_narration_llm": False,
                    "enable_provider_runtime_narration": False,
                    "enable_narration_retry": False,
                },
            },
        }
        return {
            "ok": True,
            "narration": fixture["narration"],
            "npc": deepcopy(fixture["npc"]),
            "turn_contract": contract,
            "simulation_state": deepcopy(state),
            "result": nested,
            "session": session,
        }

    return _base


def _run(turns: int, *, session_id: str) -> tuple[str, dict[str, Any]]:
    state: dict[str, Any] = {
        "session_id": session_id,
        "scene_id": "endurance-tavern",
        "location_id": "tavern",
        "turn_index": 0,
        "tick": 0,
        "response_rollout_stage": "canonical_default",
        "response_soft_truth": {"truths": [], "events": []},
    }
    base = _base_turn_factory(state)
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    category_counts = {category: 0 for category in _CATEGORIES}
    peak_truths = 0

    for turn in range(1, turns + 1):
        fixture = _turn_fixture(turn)
        started = time.perf_counter()
        payload = apply_turn(
            session_id,
            fixture["input"],
            _base_apply_turn=base,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed_ms)
        category_counts[fixture["category"]] += 1

        narration_payload = payload.get("narration_payload") or {}
        canonical = narration_payload.get("canonical_response") or {}
        if narration_payload.get("canonical_response_source") != "rpg_response_generator_v1":
            raise RuntimeError(f"missing_canonical_source_at_turn:{turn}")
        if not canonical.get("quality_report", {}).get("ok"):
            raise RuntimeError(f"quality_gate_failed_at_turn:{turn}")
        decisions = canonical.get("metadata", {}).get("hard_gate_decisions") or []
        if not decisions or not all(row.get("passed") is True for row in decisions):
            raise RuntimeError(f"hard_gate_failed_at_turn:{turn}")
        if not str(payload.get("narration") or "").strip():
            raise RuntimeError(f"empty_visible_narration_at_turn:{turn}")

        soft_truth = payload.get("response_soft_truth") or state.get("response_soft_truth") or {}
        if isinstance(soft_truth, dict):
            state["response_soft_truth"] = deepcopy(soft_truth)
            peak_truths = max(peak_truths, len(soft_truth.get("truths") or []))
        rows.append(
            {
                "turn": turn,
                "category": fixture["category"],
                "visible": payload.get("narration"),
                "candidate_source": canonical.get("metadata", {}).get("candidate_source"),
                "forward_strategy": canonical.get("metadata", {}).get("recovery_plan", {}).get("forward_strategy"),
            }
        )

    digest = hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    first_window = latencies[: max(1, turns // 10)]
    last_window = latencies[-max(1, turns // 10) :]
    first_median = statistics.median(first_window)
    last_median = statistics.median(last_window)
    drift_ratio = last_median / max(first_median, 0.001)
    p95_index = min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))
    p95_ms = sorted(latencies)[p95_index]
    report = {
        "format_version": "rpg_response_runtime_endurance_v1",
        "turns": turns,
        "digest": digest,
        "category_counts": category_counts,
        "peak_soft_truth_records": peak_truths,
        "latency": {
            "first_window_median_ms": round(first_median, 3),
            "last_window_median_ms": round(last_median, 3),
            "drift_ratio": round(drift_ratio, 3),
            "p95_ms": round(p95_ms, 3),
            "max_ms": round(max(latencies), 3),
        },
    }
    return digest, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run canonical public apply_turn endurance and replay checks."
    )
    parser.add_argument("--turns", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    turns = max(1, int(args.turns))

    first_digest, first = _run(turns, session_id="response-endurance-a")
    second_digest, second = _run(turns, session_id="response-endurance-b")
    issues: list[str] = []
    if first_digest != second_digest:
        issues.append("replay_digest_mismatch")
    if first["peak_soft_truth_records"] > 12 or second["peak_soft_truth_records"] > 12:
        issues.append("soft_truth_growth_unbounded")
    if first["latency"]["drift_ratio"] > 3.0 or second["latency"]["drift_ratio"] > 3.0:
        issues.append("latency_drift_exceeded")
    if any(count <= 0 for count in first["category_counts"].values()):
        issues.append("missing_required_category")

    report = {
        "format_version": "rpg_response_runtime_endurance_gate_v1",
        "passed": not issues,
        "issues": issues,
        "first_run": first,
        "second_run": second,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
