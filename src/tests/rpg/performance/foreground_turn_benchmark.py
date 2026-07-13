"""Provider-free benchmark for the interactive foreground RPG turn boundary.

This benchmark deliberately uses a deterministic provider stub. It is safe to run in
GitHub Actions and records orchestration/serialization evidence without contacting an
LLM endpoint. Live provider latency and quality remain local-operator checks.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from app.gateway.rpg_turn_job_mirror import _apply_turn_with_job_mirror
from app.jobs.store import InMemoryJobStore
from app.rpg.presentation.turn_response import build_turn_response_v2, turn_response_size_bytes

FORMAT_VERSION = "rpg_foreground_turn_benchmark_v1"
COMMAND = "I ask Bran how business is doing."
SESSION_ID = "session:phase0:rusty-flagon"
SUBMISSION_ID = "submit:phase0:bran-business"


class InstrumentedJobStore(InMemoryJobStore):
    """In-memory store with deterministic transition counters for benchmark evidence."""

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.transition_counts = {
            "create": 0,
            "mark_running": 0,
            "complete": 0,
            "fail": 0,
        }

    def create_job(self, *args: Any, **kwargs: Any) -> Any:
        self.transition_counts["create"] += 1
        return super().create_job(*args, **kwargs)

    def mark_running(self, *args: Any, **kwargs: Any) -> Any:
        self.transition_counts["mark_running"] += 1
        return super().mark_running(*args, **kwargs)

    def complete_job(self, *args: Any, **kwargs: Any) -> Any:
        self.transition_counts["complete"] += 1
        return super().complete_job(*args, **kwargs)

    def fail_job(self, *args: Any, **kwargs: Any) -> Any:
        self.transition_counts["fail"] += 1
        return super().fail_job(*args, **kwargs)


def run_foreground_turn_benchmark(work_dir: Path | None = None) -> dict[str, Any]:
    """Execute one deterministic Bran turn and an idempotent replay."""

    if work_dir is None:
        with tempfile.TemporaryDirectory(prefix="omnix-rpg-phase0-") as temp_dir:
            return _run_benchmark(Path(temp_dir))
    work_dir.mkdir(parents=True, exist_ok=True)
    return _run_benchmark(work_dir)


def _run_benchmark(work_dir: Path) -> dict[str, Any]:
    from app.jobs import store as job_store_module

    store = InstrumentedJobStore(work_dir / "foreground-turn-jobs")
    counters = {
        "apply_turn": 0,
        "provider_calls": 0,
        "session_loads": 0,
        "session_saves": 0,
    }

    def deterministic_apply_turn(session_id: str, command: str, *_: Any, **__: Any) -> dict[str, Any]:
        counters["apply_turn"] += 1
        counters["session_loads"] += 1
        counters["provider_calls"] += 1
        counters["session_saves"] += 1
        return {
            "ok": True,
            "turn_id": "turn:phase0:1",
            "interaction_id": "interaction:phase0:1",
            "tick": 1,
            "player_input": command,
            "final_narration": "Bran sets his polishing rag beside the till before answering.",
            "npc": {
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "line": (
                    "Steady enough. Rooms, food, and rumors keep the Rusty Flagon open, "
                    "though the old road has been quieter than I like."
                ),
            },
            "stateful": False,
            "semantic_action_type": "npc_interpretive_dialogue",
            "semantic_family": "dialogue",
            "llm_called": True,
            "llm_purpose": "dialogue",
            "source": "phase0_deterministic_provider_stub",
            "manual_turn_stage_timing": {
                "provider_ms": 0.0,
                "runtime_ms": 0.0,
                "persistence_ms": 0.0,
            },
        }

    original_default_job_store = job_store_module.default_job_store
    job_store_module.default_job_store = lambda: store
    started = time.perf_counter()
    try:
        first = _apply_turn_with_job_mirror(
            deterministic_apply_turn,
            SESSION_ID,
            COMMAND,
            submission_id=SUBMISSION_ID,
        )
        replay = _apply_turn_with_job_mirror(
            deterministic_apply_turn,
            SESSION_ID,
            COMMAND,
            submission_id=SUBMISSION_ID,
        )
    finally:
        job_store_module.default_job_store = original_default_job_store
    orchestration_ms = (time.perf_counter() - started) * 1000.0

    session = {
        "manifest": {
            "session_id": SESSION_ID,
            "title": "Rusty Flagon Phase 0 benchmark",
            "turn_count": 1,
        },
        "runtime_state": {
            "interaction_seq": 1,
            "state_revision": 0,
        },
        "state": {
            "scene": {"location_name": "The Rusty Flagon"},
            "player": {"level": 1, "hp": 10},
        },
    }
    serialization_started = time.perf_counter()
    payload = build_turn_response_v2(
        first,
        session_id=SESSION_ID,
        command=COMMAND,
        session=session,
        trace_id="trace:phase0:bran-business",
    )
    response_bytes = turn_response_size_bytes(payload)
    serialization_ms = (time.perf_counter() - serialization_started) * 1000.0

    records = store.list_jobs()
    statuses = [
        str(getattr(getattr(record, "status", None), "value", getattr(record, "status", "")))
        for record in records
    ]
    visible_text = str(payload.get("response") or "")
    assertions = {
        "exactly_one_apply_turn": counters["apply_turn"] == 1,
        "exactly_one_provider_call": counters["provider_calls"] == 1,
        "exactly_one_session_load": counters["session_loads"] == 1,
        "exactly_one_session_save": counters["session_saves"] == 1,
        "one_completed_foreground_record": len(records) == 1 and statuses == ["completed"],
        "idempotent_replay_reused_submission": replay.get("idempotent_replay") is True
        and replay.get("submission_id") == SUBMISSION_ID,
        "idempotent_replay_reused_interaction": replay.get("interaction_id") == first.get("interaction_id"),
        "compact_response_within_limit": 0 < response_bytes <= 50_000,
        "browser_visible_bran_line": "Bran:" in visible_text and "Steady enough" in visible_text,
    }

    return {
        "format_version": FORMAT_VERSION,
        "ok": all(assertions.values()),
        "mode": "provider_free_deterministic",
        "scenario": {
            "location": "The Rusty Flagon",
            "npc": "Bran",
            "command": COMMAND,
            "session_id": SESSION_ID,
            "submission_id": SUBMISSION_ID,
        },
        "counts": {
            "apply_turn": counters["apply_turn"],
            "provider_calls": counters["provider_calls"],
            "session_loads": counters["session_loads"],
            "session_saves": counters["session_saves"],
            "interaction_seq": 1,
            "simulation_tick": 1,
        },
        "job": {
            "record_count": len(records),
            "statuses": statuses,
            "transitions": dict(store.transition_counts),
        },
        "response": {
            "contract_version": payload.get("contract_version"),
            "bytes": response_bytes,
            "serialization_ms": round(serialization_ms, 3),
            "browser_visible_text": visible_text,
        },
        "timing_ms": {
            "provider_stub": 0.0,
            "foreground_orchestration": round(orchestration_ms, 3),
            "serialization": round(serialization_ms, 3),
        },
        "replay": {
            "idempotent_replay": replay.get("idempotent_replay") is True,
            "submission_id": replay.get("submission_id"),
            "interaction_id": replay.get("interaction_id"),
        },
        "assertions": assertions,
        "ci_policy": {
            "live_provider_used": False,
            "latency_acceptance_enforced_here": False,
            "reason": "Live provider quality and latency are local-operator evidence only.",
        },
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_foreground_turn_benchmark()
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
