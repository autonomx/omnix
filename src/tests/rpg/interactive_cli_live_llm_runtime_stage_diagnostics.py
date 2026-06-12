"""Phase 14.15 — runtime-embedded stage diagnostics for live endurance artifacts.

Phase 14.14 aggregates manual-harness slowest-stage samples, but those samples
include overlapping events such as ``manual_harness_total`` and
``manual_harness_apply_turn``. This analyzer reads the runtime-embedded
``manual_turn_stage_timing`` payload from each ``interactive-transcript.json``
turn instead. Those fields are emitted by the interactive first-call runtime and
are non-overlapping enough to explain the apply-turn body without changing live
runtime behavior.
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

LIVE_ENDURANCE_RUNTIME_STAGE_DIAGNOSTICS_VERSION = "rpg_live_endurance_runtime_stage_diagnostics_v1"
LIVE_ENDURANCE_RUNTIME_STAGE_DIAGNOSTICS_STATUS_MARKER = "RPG_LIVE_ENDURANCE_RUNTIME_STAGE_DIAGNOSTICS"
DEFAULT_LIVE_ENDURANCE_DIR = Path("resources") / "data" / "test-results" / "live-llm-endurance-matrix"
DEFAULT_DIAGNOSTICS_FILENAME = "live-endurance-runtime-stage-diagnostics.json"
DEFAULT_AGGREGATE_FILENAME = "live-quality-aggregate.json"

RUNTIME_STAGE_KEYS: tuple[str, ...] = (
    "pre_runtime_intent_llm_ms",
    "deterministic_runtime_apply_ms",
    "grounding_validation_ms",
    "repair_ms",
    "state_snapshot_ms",
    "deferred_enqueue_ms",
)


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


def _transcript_files(output_dir: Path) -> list[Path]:
    if not output_dir.exists():
        return []
    direct = output_dir / "interactive-transcript.json"
    if direct.exists():
        return [direct]
    return sorted(path for path in output_dir.glob("*/interactive-transcript.json") if path.is_file())


def _performance_for_transcript(transcript_path: Path) -> dict[str, Any]:
    return _read_json(transcript_path.with_name("interactive-performance.json"))


def _runtime_timing_from_turn(turn: Mapping[str, Any]) -> dict[str, Any]:
    raw = _d(turn.get("raw_result") or turn.get("result"))
    nested = _d(raw.get("result"))
    candidates = (
        turn.get("manual_turn_stage_timing"),
        raw.get("manual_turn_stage_timing"),
        nested.get("manual_turn_stage_timing"),
        _d(turn.get("interactive_cli_performance")).get("runtime_stage_timing"),
    )
    for candidate in candidates:
        timing = _d(candidate)
        if timing:
            return timing
    return {}


def _runtime_apply_seconds_for_turn(turn: Mapping[str, Any]) -> float:
    perf = _d(turn.get("interactive_cli_performance"))
    return _f(perf.get("runtime_apply_turn_seconds"))


def _add_stage(bucket: dict[str, Any], *, seconds: float, pack: str, turn_index: Any, player_input: str) -> None:
    bucket["count"] = _i(bucket.get("count")) + 1
    bucket["total_seconds"] = round(_f(bucket.get("total_seconds")) + seconds, 4)
    bucket["max_seconds"] = round(max(_f(bucket.get("max_seconds")), seconds), 4)
    turns = _l(bucket.get("turn_indices"))
    if turn_index not in turns and len(turns) < 25:
        turns.append(turn_index)
    bucket["turn_indices"] = turns
    samples = _l(bucket.get("samples"))
    if len(samples) < 5:
        samples.append({"pack": pack, "turn_index": turn_index, "seconds": seconds, "player_input": player_input[:180]})
    bucket["samples"] = samples


def _finalize_stages(stage_totals: Mapping[str, Mapping[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, value in stage_totals.items():
        row = dict(value)
        count = max(1, _i(row.get("count")))
        row["name"] = name
        row["avg_seconds"] = round(_f(row.get("total_seconds")) / count, 4)
        rows.append(row)
    return sorted(rows, key=lambda item: (_f(item.get("total_seconds")), _f(item.get("max_seconds"))), reverse=True)[:limit]


def diagnose_live_endurance_runtime_stages(
    *,
    output_dir: str | Path | None = None,
    aggregate_path: str | Path | None = None,
    diagnostics_path: str | Path | None = None,
    update_aggregate: bool = True,
) -> dict[str, Any]:
    out = Path(output_dir) if output_dir else DEFAULT_LIVE_ENDURANCE_DIR
    aggregate_file = Path(aggregate_path) if aggregate_path else out / DEFAULT_AGGREGATE_FILENAME
    diagnostics_file = Path(diagnostics_path) if diagnostics_path else out / DEFAULT_DIAGNOSTICS_FILENAME
    files = _transcript_files(out)

    warnings: list[str] = []
    if not files:
        warnings.append("live_endurance_runtime_stage_no_transcript_files")

    stage_buckets: dict[str, dict[str, Any]] = {}
    pack_rows: list[dict[str, Any]] = []
    completed_turns = 0
    turns_with_timing = 0
    runtime_apply_total = 0.0
    embedded_stage_total = 0.0

    for transcript_path in files:
        transcript = _read_json(transcript_path)
        performance = _performance_for_transcript(transcript_path)
        phase_totals = _d(performance.get("phase_totals_seconds"))
        pack = _pack_name(transcript_path.parent)
        turns = [_d(turn) for turn in _l(transcript.get("turns"))]
        pack_stage_buckets: dict[str, dict[str, Any]] = {}
        pack_runtime_apply_total = _f(phase_totals.get("runtime_apply_turn_seconds"))
        if pack_runtime_apply_total <= 0:
            pack_runtime_apply_total = round(sum(_runtime_apply_seconds_for_turn(turn) for turn in turns), 4)
        pack_embedded_total = 0.0
        pack_turns_with_timing = 0

        for turn in turns:
            timing = _runtime_timing_from_turn(turn)
            if not timing:
                continue
            pack_turns_with_timing += 1
            turns_with_timing += 1
            turn_index = turn.get("turn_index")
            player_input = _s(turn.get("player_input"))
            for key in RUNTIME_STAGE_KEYS:
                seconds = round(_f(timing.get(key)) / 1000.0, 4)
                if seconds <= 0:
                    continue
                pack_embedded_total = round(pack_embedded_total + seconds, 4)
                embedded_stage_total = round(embedded_stage_total + seconds, 4)
                _add_stage(stage_buckets.setdefault(key, {}), seconds=seconds, pack=pack, turn_index=turn_index, player_input=player_input)
                _add_stage(pack_stage_buckets.setdefault(key, {}), seconds=seconds, pack=pack, turn_index=turn_index, player_input=player_input)

        if turns and not pack_turns_with_timing:
            warnings.append(f"live_endurance_runtime_stage_no_embedded_timing:{pack}")
        completed_turns += len(turns)
        runtime_apply_total = round(runtime_apply_total + pack_runtime_apply_total, 4)
        pack_rows.append({
            "pack": pack,
            "transcript_path": str(transcript_path),
            "performance_path": str(transcript_path.with_name("interactive-performance.json")),
            "completed_turns": len(turns),
            "turns_with_runtime_stage_timing": pack_turns_with_timing,
            "runtime_apply_total_seconds": round(pack_runtime_apply_total, 4),
            "runtime_embedded_stage_total_seconds": round(pack_embedded_total, 4),
            "runtime_embedded_stage_share_of_apply": round(pack_embedded_total / pack_runtime_apply_total, 4) if pack_runtime_apply_total else 0.0,
            "top_runtime_stages": _finalize_stages(pack_stage_buckets, limit=10),
        })

    result = {
        "format_version": LIVE_ENDURANCE_RUNTIME_STAGE_DIAGNOSTICS_VERSION,
        "ok": True,
        "output_dir": str(out),
        "aggregate_path": str(aggregate_file),
        "diagnostics_path": str(diagnostics_file),
        "pack_count": len(files),
        "completed_turns": completed_turns,
        "turns_with_runtime_stage_timing": turns_with_timing,
        "runtime_apply_total_seconds": round(runtime_apply_total, 4),
        "runtime_embedded_stage_total_seconds": round(embedded_stage_total, 4),
        "runtime_embedded_stage_share_of_apply": round(embedded_stage_total / runtime_apply_total, 4) if runtime_apply_total else 0.0,
        "top_runtime_stages": _finalize_stages(stage_buckets, limit=20),
        "packs": pack_rows,
        "warnings": sorted(set(warnings))[:100],
        "failures": [],
        "note": "Runtime stage timing is read from manual_turn_stage_timing embedded in each transcript raw_result; unlike manual-harness slowest-stage samples, these stage totals do not include manual_harness_total overlap.",
    }
    _write_json(diagnostics_file, result)

    if update_aggregate and aggregate_file.exists():
        aggregate = _read_json(aggregate_file)
        aggregate["live_endurance_runtime_stage_diagnostics"] = result
        aggregate["runtime_stage_diagnostics_path"] = str(diagnostics_file)
        aggregate["runtime_stage_diagnostics_warning_count"] = len(result["warnings"])
        aggregate["runtime_stage_diagnostics_warning_types"] = list(result["warnings"])
        _write_json(aggregate_file, aggregate)

    return result


def render_runtime_stage_diagnostics_status_marker(result: Mapping[str, Any]) -> str:
    top = _d(_l(result.get("top_runtime_stages"))[0]) if _l(result.get("top_runtime_stages")) else {}
    return (
        f"[{LIVE_ENDURANCE_RUNTIME_STAGE_DIAGNOSTICS_STATUS_MARKER}] "
        f"ok={'true' if result.get('ok') else 'false'} "
        f"pack_count={_i(result.get('pack_count'))} "
        f"turns_with_timing={_i(result.get('turns_with_runtime_stage_timing'))} "
        f"embedded_share={_f(result.get('runtime_embedded_stage_share_of_apply')):.3f} "
        f"top_stage={_s(top.get('name') or 'none')} "
        f"top_total={_f(top.get('total_seconds')):.3f}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate runtime-embedded stage diagnostics from live endurance transcripts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_LIVE_ENDURANCE_DIR))
    parser.add_argument("--aggregate-path", default="")
    parser.add_argument("--diagnostics-path", default="")
    parser.add_argument("--no-update-aggregate", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = diagnose_live_endurance_runtime_stages(
        output_dir=args.output_dir,
        aggregate_path=args.aggregate_path or None,
        diagnostics_path=args.diagnostics_path or None,
        update_aggregate=not bool(args.no_update_aggregate),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True, default=str))
    print(render_runtime_stage_diagnostics_status_marker(result), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
