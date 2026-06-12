"""Phase 14.14 — post-run apply-turn subphase diagnostics for live endurance artifacts.

The 25-turn endurance matrix already writes coarse timing in
``interactive-performance.json``. The largest bucket is usually
``runtime_apply_turn_seconds``. This post-run analyzer drills into the existing
manual-harness slowest-stage samples embedded in slow-turn rows and writes a
separate diagnostics artifact without changing live runtime behavior.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

THIS_FILE = Path(__file__).resolve()
for path in (str(THIS_FILE.parents[1]), str(THIS_FILE.parents[2]), str(THIS_FILE.parents[3])):
    if path not in sys.path:
        sys.path.insert(0, path)

LIVE_ENDURANCE_APPLY_TURN_DIAGNOSTICS_VERSION = "rpg_live_endurance_apply_turn_diagnostics_v1"
LIVE_ENDURANCE_APPLY_TURN_DIAGNOSTICS_STATUS_MARKER = "RPG_LIVE_ENDURANCE_APPLY_TURN_DIAGNOSTICS"
DEFAULT_LIVE_ENDURANCE_DIR = Path("resources") / "data" / "test-results" / "live-llm-endurance-matrix"
DEFAULT_DIAGNOSTICS_FILENAME = "live-endurance-apply-turn-diagnostics.json"
DEFAULT_AGGREGATE_FILENAME = "live-quality-aggregate.json"


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _l(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _pack_name(path: Path) -> str:
    name = path.name
    parts = name.split("-", 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[1]
    return name


def _stage_event(stage: Mapping[str, Any]) -> str:
    for key in ("event", "stage", "name", "phase"):
        value = _s(stage.get(key)).strip()
        if value:
            return value
    return "unknown_manual_harness_stage"


def _stage_seconds(stage: Mapping[str, Any]) -> float:
    for key in ("elapsed_seconds", "seconds", "duration_seconds", "duration"):
        value = _f(stage.get(key), -1.0)
        if value >= 0:
            return round(value, 4)
    return 0.0


def categorize_apply_turn_stage(event: str) -> str:
    text = _s(event).lower()
    if any(token in text for token in ("provider", "llm", "generate", "completion", "model", "gateway")):
        return "provider_or_llm"
    if any(token in text for token in ("session", "save", "load", "persist", "storage")):
        return "session_state_io"
    if any(token in text for token in ("simulation", "apply", "turn", "contract", "state")):
        return "simulation_apply"
    if any(token in text for token in ("narration", "present", "response", "render")):
        return "narration_or_presentation"
    if any(token in text for token in ("memory", "journal", "quest", "npc", "social")):
        return "world_memory_or_quest"
    if any(token in text for token in ("repair", "validate", "ground", "guard")):
        return "validation_or_repair"
    return "other"


def _add_bucket(bucket: dict[str, Any], *, seconds: float, pack: str, turn_index: Any, player_input: str, event: str) -> None:
    bucket["count"] = _i(bucket.get("count")) + 1
    bucket["total_seconds"] = round(_f(bucket.get("total_seconds")) + seconds, 4)
    bucket["max_seconds"] = round(max(_f(bucket.get("max_seconds")), seconds), 4)
    turns = _l(bucket.get("turn_indices"))
    if turn_index not in turns and len(turns) < 25:
        turns.append(turn_index)
    bucket["turn_indices"] = turns
    samples = _l(bucket.get("samples"))
    if len(samples) < 5:
        samples.append({"pack": pack, "turn_index": turn_index, "event": event, "seconds": seconds, "player_input": player_input[:180]})
    bucket["samples"] = samples


def _finalize_buckets(buckets: Mapping[str, Mapping[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, value in buckets.items():
        row = dict(value)
        count = max(1, _i(row.get("count")))
        row["name"] = name
        row["avg_seconds"] = round(_f(row.get("total_seconds")) / count, 4)
        rows.append(row)
    return sorted(rows, key=lambda item: (_f(item.get("total_seconds")), _f(item.get("max_seconds"))), reverse=True)[:limit]


def _performance_files(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    direct = output_dir / "interactive-performance.json"
    if direct.exists():
        return [direct]
    return sorted(path for path in output_dir.glob("*/interactive-performance.json") if path.is_file())


def diagnose_live_endurance_apply_turns(
    *,
    output_dir: str | Path | None = None,
    aggregate_path: str | Path | None = None,
    diagnostics_path: str | Path | None = None,
    update_aggregate: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir) if output_dir else DEFAULT_LIVE_ENDURANCE_DIR
    aggregate_file = Path(aggregate_path) if aggregate_path else out / DEFAULT_AGGREGATE_FILENAME
    diagnostics_file = Path(diagnostics_path) if diagnostics_path else out / DEFAULT_DIAGNOSTICS_FILENAME
    files = _performance_files(out)

    warnings: list[str] = []
    if not files:
        warnings.append("live_endurance_apply_turn_no_performance_files")

    event_buckets: dict[str, dict[str, Any]] = {}
    category_buckets: dict[str, dict[str, Any]] = {}
    pack_rows: list[dict[str, Any]] = []
    completed_turns = slow_turn_count = 0
    runtime_apply_total = sampled_stage_total = 0.0

    for performance_path in files:
        performance = _read_json(performance_path)
        pack = _pack_name(performance_path.parent)
        phase_totals = _d(performance.get("phase_totals_seconds"))
        phase_avg = _d(performance.get("phase_avg_seconds"))
        pack_completed = _i(performance.get("completed_turns"))
        pack_slow = _i(performance.get("slow_turn_count"))
        pack_runtime_apply_total = _f(phase_totals.get("runtime_apply_turn_seconds"))
        pack_sampled_total = 0.0
        pack_event_buckets: dict[str, dict[str, Any]] = {}

        for slow_turn in _l(performance.get("slow_turns")):
            slow_turn = _d(slow_turn)
            turn_index = slow_turn.get("turn_index")
            player_input = _s(slow_turn.get("player_input"))
            for stage in _l(slow_turn.get("manual_harness_slowest_stages")):
                stage = _d(stage)
                event = _stage_event(stage)
                seconds = _stage_seconds(stage)
                if seconds <= 0:
                    continue
                category = categorize_apply_turn_stage(event)
                pack_sampled_total = round(pack_sampled_total + seconds, 4)
                _add_bucket(event_buckets.setdefault(event, {"category": category}), seconds=seconds, pack=pack, turn_index=turn_index, player_input=player_input, event=event)
                _add_bucket(category_buckets.setdefault(category, {"category": category}), seconds=seconds, pack=pack, turn_index=turn_index, player_input=player_input, event=event)
                _add_bucket(pack_event_buckets.setdefault(event, {"category": category}), seconds=seconds, pack=pack, turn_index=turn_index, player_input=player_input, event=event)

        if pack_slow and pack_sampled_total <= 0:
            warnings.append(f"live_endurance_apply_turn_no_manual_stage_samples:{pack}")

        completed_turns += pack_completed
        slow_turn_count += pack_slow
        runtime_apply_total = round(runtime_apply_total + pack_runtime_apply_total, 4)
        sampled_stage_total = round(sampled_stage_total + pack_sampled_total, 4)
        pack_rows.append({
            "pack": pack,
            "performance_path": str(performance_path),
            "completed_turns": pack_completed,
            "slow_turn_count": pack_slow,
            "runtime_apply_total_seconds": round(pack_runtime_apply_total, 4),
            "runtime_apply_avg_seconds": _f(phase_avg.get("runtime_apply_turn_seconds")),
            "sampled_stage_total_seconds": round(pack_sampled_total, 4),
            "sampled_stage_share_of_runtime_apply": round(pack_sampled_total / pack_runtime_apply_total, 4) if pack_runtime_apply_total else 0.0,
            "top_apply_turn_events": _finalize_buckets(pack_event_buckets, limit=10),
        })

    result = {
        "format_version": LIVE_ENDURANCE_APPLY_TURN_DIAGNOSTICS_VERSION,
        "ok": True,
        "output_dir": str(out),
        "aggregate_path": str(aggregate_file),
        "diagnostics_path": str(diagnostics_file),
        "pack_count": len(files),
        "completed_turns": completed_turns,
        "slow_turn_count": slow_turn_count,
        "runtime_apply_total_seconds": round(runtime_apply_total, 4),
        "sampled_stage_total_seconds": round(sampled_stage_total, 4),
        "sampled_stage_share_of_runtime_apply": round(sampled_stage_total / runtime_apply_total, 4) if runtime_apply_total else 0.0,
        "top_apply_turn_events": _finalize_buckets(event_buckets, limit=20),
        "top_apply_turn_categories": _finalize_buckets(category_buckets, limit=20),
        "packs": pack_rows,
        "warnings": sorted(set(warnings))[:100],
        "failures": [],
        "note": "Manual-harness stages are sampled from slow-turn rows, so totals explain sampled hotspots inside runtime_apply_turn_seconds rather than every substep of every turn.",
    }
    _write_json(diagnostics_file, result)

    if update_aggregate and aggregate_file.exists():
        aggregate = _read_json(aggregate_file)
        aggregate["live_endurance_apply_turn_diagnostics"] = result
        aggregate["apply_turn_diagnostics_path"] = str(diagnostics_file)
        aggregate["apply_turn_diagnostics_warning_count"] = len(result["warnings"])
        aggregate["apply_turn_diagnostics_warning_types"] = list(result["warnings"])
        _write_json(aggregate_file, aggregate)

    return result


def render_apply_turn_diagnostics_status_marker(result: Mapping[str, Any]) -> str:
    top_events = _l(result.get("top_apply_turn_events"))
    top = _d(top_events[0]) if top_events else {}
    return (
        f"[{LIVE_ENDURANCE_APPLY_TURN_DIAGNOSTICS_STATUS_MARKER}] "
        f"ok={'true' if result.get('ok') else 'false'} "
        f"pack_count={_i(result.get('pack_count'))} "
        f"slow_turn_count={_i(result.get('slow_turn_count'))} "
        f"sampled_share={_f(result.get('sampled_stage_share_of_runtime_apply')):.3f} "
        f"top_event={_s(top.get('name') or 'none')} "
        f"top_total={_f(top.get('total_seconds')):.3f}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate apply-turn subphase diagnostics from live endurance artifacts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_LIVE_ENDURANCE_DIR))
    parser.add_argument("--aggregate-path", default="")
    parser.add_argument("--diagnostics-path", default="")
    parser.add_argument("--no-update-aggregate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = diagnose_live_endurance_apply_turns(
        output_dir=args.output_dir,
        aggregate_path=args.aggregate_path or None,
        diagnostics_path=args.diagnostics_path or None,
        update_aggregate=not bool(args.no_update_aggregate),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_apply_turn_diagnostics_status_marker(result), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
