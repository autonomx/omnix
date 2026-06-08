"""Targeted probes for late-turn runtime recursion/performance failures.

These helpers are intentionally small and provider-free.  They exercise the same
classes of operations that can dominate the live runtime turn path when a
long-run state accumulates recursive diagnostic payloads: structural copying,
JSON-safe walking, and exception formatting.
"""
from __future__ import annotations

import copy
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

SOURCE = "autoplay_runtime_recursion_perf_probe_v1"
SUMMARY_NAME = "autoplay-runtime-recursion-perf-probe.json"


def make_self_referential_turn_payload(*, depth: int = 12, fanout: int = 3) -> Dict[str, Any]:
    root: Dict[str, Any] = {
        "ok": False,
        "turn_index": 59,
        "runtime_name": "targeted_probe_runtime",
        "manual_stage_trace": [],
        "turn_perf_trace": [],
    }
    cursor = root
    for index in range(max(1, depth)):
        child = {
            "index": index,
            "items": [{"slot": slot, "parent_ref": root} for slot in range(max(1, fanout))],
        }
        cursor["next"] = child
        cursor = child
    cursor["cycle"] = root
    root["manual_stage_trace"].append({"event": "cycle_attached", "payload": root})
    root["turn_perf_trace"].append({"event": "cycle_attached", "payload": root})
    return root


def bounded_json_clone(value: Any, *, max_depth: int = 12, max_items: int = 40) -> Any:
    seen: set[int] = set()

    def visit(node: Any, depth: int) -> Any:
        if node is None or isinstance(node, (str, int, float, bool)):
            return node
        if depth >= max_depth:
            return {"__truncated__": True, "reason": "max_depth"}
        node_id = id(node)
        if node_id in seen:
            return {"__cycle__": True}
        seen.add(node_id)
        try:
            if isinstance(node, Mapping):
                result: Dict[str, Any] = {}
                for index, (key, nested) in enumerate(node.items()):
                    if index >= max_items:
                        result["__truncated_items__"] = len(node) - max_items
                        break
                    result[str(key)] = visit(nested, depth + 1)
                return result
            if isinstance(node, (list, tuple, set)):
                items = list(node)
                result = [visit(item, depth + 1) for item in items[:max_items]]
                if len(items) > max_items:
                    result.append({"__truncated_items__": len(items) - max_items})
                return result
            return repr(node)
        finally:
            seen.discard(node_id)

    return visit(value, 0)


def measure_operation(name: str, func: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        result = func()
        ok = True
        error_type = None
        error = None
    except BaseException as exc:  # diagnostics only
        result = None
        ok = False
        error_type = type(exc).__name__
        error = str(exc)
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "name": name,
        "ok": ok,
        "elapsed_ms": elapsed_ms,
        "error_type": error_type,
        "error": error,
        "result_type": type(result).__name__ if result is not None else None,
        "source": SOURCE,
    }


def run_targeted_recursion_perf_probe(*, output_dir: str | Path | None = None, depth: int = 16, fanout: int = 3) -> Dict[str, Any]:
    payload = make_self_referential_turn_payload(depth=depth, fanout=fanout)
    operations = [
        measure_operation("copy.deepcopy", lambda: copy.deepcopy(payload)),
        measure_operation("bounded_json_clone", lambda: bounded_json_clone(payload)),
        measure_operation("json.dumps_bounded_clone", lambda: json.dumps(bounded_json_clone(payload), sort_keys=True)),
    ]
    try:
        raise RuntimeError("targeted probe exception")
    except RuntimeError:
        operations.append(measure_operation("traceback.format_exc", traceback.format_exc))
    summary = {
        "ok": True,
        "source": SOURCE,
        "depth": depth,
        "fanout": fanout,
        "operations": operations,
        "slow_operations": [op for op in operations if float(op.get("elapsed_ms") or 0.0) > 250.0],
        "failed_operations": [op for op in operations if not op.get("ok")],
    }
    if output_dir is not None:
        path = Path(output_dir) / SUMMARY_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        summary["path"] = str(path)
    return summary


def run_targeted_recursion_perf_probe_from_argv(argv: Iterable[str]) -> Dict[str, Any]:
    output_dir: Optional[Path] = None
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            output_dir = Path(args[index + 1])
        elif value.startswith("--output-dir="):
            output_dir = Path(value.split("=", 1)[1])
    return run_targeted_recursion_perf_probe(output_dir=output_dir)
