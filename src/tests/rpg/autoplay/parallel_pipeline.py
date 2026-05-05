from __future__ import annotations

import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.narration.runtime_narration_contract import build_runtime_narration_payload

from tests.rpg.autoplay.checkpoints import validate_save_load_checkpoint
from tests.rpg.autoplay.performance import elapsed_ms, now_perf
from tests.rpg.autoplay.progress import state_digest


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def freeze_snapshot(value: Any) -> Any:
    """Create a worker-owned copy so background jobs never touch live state."""
    return deepcopy(value)


def _deferred_narration_job(
    *,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    started = now_perf()
    before_digest = state_digest(_safe_dict(simulation_state))
    frozen_state = freeze_snapshot(_safe_dict(simulation_state))
    try:
        payload = build_runtime_narration_payload(
            provider=provider,
            player_action=player_action,
            simulation_state=frozen_state,
            turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
            prefer_provider=bool(prefer_provider),
        )
        after_digest = state_digest(_safe_dict(simulation_state))
        return {
            "ok": True,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "ready",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "narration": _safe_str(payload.get("narration")),
            "npc": _safe_dict(payload.get("npc")),
            "narration_payload": payload,
            "worker_ms": elapsed_ms(started),
            "state_digest_before": before_digest,
            "state_digest_after": after_digest,
            "mutated_authoritative_snapshot": before_digest != after_digest,
        }
    except Exception as exc:
        return {
            "ok": False,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "error",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "worker_ms": elapsed_ms(started),
        }


def _checkpoint_job(
    *,
    session_id: str,
    turn_index: int,
    checkpoint_dir: Any,
    simulation_state: Dict[str, Any],
) -> Dict[str, Any]:
    started = now_perf()
    try:
        result = validate_save_load_checkpoint(
            session_id=session_id,
            turn_index=turn_index,
            checkpoint_dir=checkpoint_dir,
            simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
        )
        result["kind"] = "checkpoint"
        result["turn_index"] = turn_index
        result["worker_ms"] = elapsed_ms(started)
        return result
    except Exception as exc:
        return {
            "ok": False,
            "kind": "checkpoint",
            "turn_index": turn_index,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "worker_ms": elapsed_ms(started),
        }


class AutoplayBackgroundPipeline:
    """Thread pool for non-authoritative autoplay jobs.

    The simulation turn still runs synchronously. Jobs submitted here must only
    receive frozen snapshots and may only return presentation, diagnostic,
    checkpoint, or report artifacts.
    """

    def __init__(self, *, background_workers: int = 4, provider_workers: int = 1) -> None:
        self.background_workers = max(1, int(background_workers or 1))
        self.provider_workers = max(1, int(provider_workers or 1))
        self._background_executor = ThreadPoolExecutor(
            max_workers=self.background_workers,
            thread_name_prefix="rpg-autoplay-bg",
        )
        self._provider_executor = ThreadPoolExecutor(
            max_workers=self.provider_workers,
            thread_name_prefix="rpg-autoplay-provider",
        )
        self._futures: List[Future] = []

    def submit_deferred_narration(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"narration:{session_id}:{turn_index}"
        future = self._provider_executor.submit(
            _deferred_narration_job,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            prefer_provider=prefer_provider,
        )
        self._futures.append(future)
        return job_id

    def submit_checkpoint(
        self,
        *,
        session_id: str,
        turn_index: int,
        checkpoint_dir: Any,
        simulation_state: Dict[str, Any],
    ) -> str:
        job_id = f"checkpoint:{session_id}:{turn_index}"
        future = self._background_executor.submit(
            _checkpoint_job,
            session_id=session_id,
            turn_index=turn_index,
            checkpoint_dir=checkpoint_dir,
            simulation_state=freeze_snapshot(simulation_state),
        )
        self._futures.append(future)
        return job_id

    def drain(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        futures = list(self._futures)
        self._futures.clear()
        for future in as_completed(futures):
            try:
                value = future.result()
                results.append(
                    value if isinstance(value, dict)
                    else {"ok": False, "error": "worker_returned_non_dict"}
                )
            except Exception as exc:
                results.append(
                    {
                        "ok": False,
                        "kind": "unknown",
                        "error": f"{type(exc).__name__}: {exc}",
                        "traceback": traceback.format_exc(),
                    }
                )
        return results

    def shutdown(self) -> None:
        self._provider_executor.shutdown(wait=True)
        self._background_executor.shutdown(wait=True)


def attach_background_results_to_transcript(
    transcript: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_turn = {
        int(row.get("turn_index") or 0): row
        for row in transcript
        if isinstance(row, dict)
    }
    summary = {
        "total_jobs": len(results),
        "ok_jobs": 0,
        "failed_jobs": 0,
        "narration_jobs": 0,
        "checkpoint_jobs": 0,
        "background_job_seconds": 0.0,
        "errors": [],
    }
    for result in results:
        if result.get("ok"):
            summary["ok_jobs"] += 1
        else:
            summary["failed_jobs"] += 1
            if result.get("error"):
                summary["errors"].append(result.get("error"))

        summary["background_job_seconds"] += float(result.get("worker_ms") or 0.0) / 1000.0
        turn_index = int(result.get("turn_index") or 0)
        row = by_turn.get(turn_index)
        if not row:
            continue

        if result.get("kind") == "deferred_narration":
            summary["narration_jobs"] += 1
            row["deferred_narration_result"] = result
            row["narration_status"] = result.get("narration_status")
            if result.get("ok") and result.get("narration"):
                row["narration"] = result.get("narration")
                row.setdefault("turn_result", {})["narration"] = result.get("narration")
                row.setdefault("turn_result", {})["structured_narration"] = (
                    result.get("narration_payload") or {}
                )
                row.setdefault("turn_result", {})["narration_payload"] = (
                    result.get("narration_payload") or {}
                )
        elif result.get("kind") == "checkpoint":
            summary["checkpoint_jobs"] += 1
            row["save_load_checkpoint"] = result

    summary["background_job_seconds"] = round(summary["background_job_seconds"], 3)
    return summary