"""Split helpers for autoplay background pipeline."""
from __future__ import annotations

# ruff: noqa: F401,F403,F405,F811
from tests.rpg.autoplay.parallel_pipeline_common import *
from tests.rpg.autoplay.parallel_pipeline_narration import *
from tests.rpg.autoplay.parallel_pipeline_provider_payloads import *
from tests.rpg.autoplay.parallel_pipeline_n11616 import *
from tests.rpg.autoplay.parallel_pipeline_n116161 import *
from tests.rpg.autoplay.parallel_pipeline_n11620 import *
from tests.rpg.autoplay.parallel_pipeline_jobs import *

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
        self._future_job_ids: Dict[Future, str] = {}
        self._job_futures: Dict[str, Future] = {}
        self._completed_results: Dict[str, Dict[str, Any]] = {}

    def _register_future(self, job_id: str, future: Future) -> str:
        self._futures.append(future)
        self._future_job_ids[future] = job_id
        self._job_futures[job_id] = future
        return job_id

    def _finalize_future_result(self, future: Future) -> Dict[str, Any]:
        job_id = self._future_job_ids.get(future, "")
        try:
            value = future.result()
            result = (
                value if isinstance(value, dict)
                else {"ok": False, "kind": "unknown", "error": "worker_returned_non_dict"}
            )
        except Exception as exc:
            result = {
                "ok": False,
                "kind": "unknown",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        if job_id:
            result.setdefault("job_id", job_id)
            self._completed_results[job_id] = result
            self._job_futures.pop(job_id, None)
        self._future_job_ids.pop(future, None)
        try:
            self._futures.remove(future)
        except ValueError:
            pass
        return result

    def _finalize_unfinished_future(
        self,
        future: Future,
        *,
        reason: str = "final_drain_timeout",
        cancel: bool = True,
    ) -> Dict[str, Any]:
        job_id = self._future_job_ids.get(future, "")
        cancelled = False
        if cancel:
            try:
                cancelled = bool(future.cancel())
            except Exception:
                cancelled = False
        result = {
            "ok": False,
            "kind": "background_timeout",
            "job_id": job_id,
            "error": reason,
            "cancelled": cancelled,
            "done": bool(future.done()),
        }
        if job_id:
            self._completed_results[job_id] = result
            self._job_futures.pop(job_id, None)
        self._future_job_ids.pop(future, None)
        try:
            self._futures.remove(future)
        except ValueError:
            pass
        return result

    def get_completed_result(self, job_id: str, timeout: float = 0.0) -> Dict[str, Any]:
        """Return a completed result for job_id without waiting by default."""
        if not job_id:
            return {}
        cached = self._completed_results.get(job_id)
        if isinstance(cached, dict) and cached:
            return cached
        future = self._job_futures.get(job_id)
        if future is None:
            return {}
        if timeout and timeout > 0:
            try:
                value = future.result(timeout=timeout)
                result = (
                    value if isinstance(value, dict)
                    else {"ok": False, "kind": "unknown", "error": "worker_returned_non_dict"}
                )
                result.setdefault("job_id", job_id)
                self._completed_results[job_id] = result
                self._job_futures.pop(job_id, None)
                self._future_job_ids.pop(future, None)
                try:
                    self._futures.remove(future)
                except ValueError:
                    pass
                return result
            except TimeoutError:
                return {}
            except Exception as exc:
                result = {
                    "ok": False,
                    "kind": "unknown",
                    "job_id": job_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
                self._completed_results[job_id] = result
                self._job_futures.pop(job_id, None)
                self._future_job_ids.pop(future, None)
                try:
                    self._futures.remove(future)
                except ValueError:
                    pass
                return result
        if not future.done():
            return {}
        return self._finalize_future_result(future)

    def drain_completed(self) -> List[Dict[str, Any]]:
        """Drain all currently completed futures without blocking."""
        completed: List[Dict[str, Any]] = []
        for future in list(self._futures):
            if future.done():
                completed.append(self._finalize_future_result(future))
        return completed

    def pending_job_count(self) -> int:
        return len(list(self._futures))

    def pending_job_ids(self) -> List[str]:
        return [
            self._future_job_ids.get(future, "")
            for future in list(self._futures)
            if self._future_job_ids.get(future, "")
        ]

    def executor_thread_diagnostics(self) -> Dict[str, Any]:
        provider_threads = [
            {
                "name": getattr(thread, "name", ""),
                "alive": bool(thread.is_alive()),
                "daemon": bool(thread.daemon),
            }
            for thread in list(getattr(self._provider_executor, "_threads", []) or [])
        ]
        background_threads = [
            {
                "name": getattr(thread, "name", ""),
                "alive": bool(thread.is_alive()),
                "daemon": bool(thread.daemon),
            }
            for thread in list(getattr(self._background_executor, "_threads", []) or [])
        ]
        return {
            "pending_job_count": self.pending_job_count(),
            "pending_job_ids": self.pending_job_ids()[:50],
            "provider_threads": provider_threads,
            "background_threads": background_threads,
            "alive_provider_thread_count": sum(1 for row in provider_threads if row.get("alive")),
            "alive_background_thread_count": sum(1 for row in background_threads if row.get("alive")),
        }

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
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _deferred_narration_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            prefer_provider=prefer_provider,
        )
        return self._register_future(job_id, future)

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
        return self._register_future(job_id, future)

    def submit_deferred_advisory(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        turn_contract: Dict[str, Any],
        semantic_action_record: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"advisory:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _deferred_advisory_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
        )
        return self._register_future(job_id, future)

    def submit_combined_background_llm(
        self,
        *,
        provider: Any,
        session_id: str,
        turn_index: int,
        player_action: str,
        simulation_state: Dict[str, Any],
        runtime_state: Dict[str, Any] | None = None,
        turn_contract: Dict[str, Any],
        semantic_action_record: Dict[str, Any],
        prefer_provider: bool = True,
    ) -> str:
        job_id = f"combined_background_llm:{session_id}:{turn_index}"
        queued_at = now_perf()
        future = self._provider_executor.submit(
            _combined_background_llm_job,
            queued_at=queued_at,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            runtime_state=freeze_snapshot(runtime_state or {}),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
        )
        self._register_future(job_id, future)
        print(f"Submitted combined background LLM job {job_id}")
        return job_id

    def drain(
        self,
        *,
        timeout_seconds: float | None = None,
        cancel_unfinished: bool = False,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        futures = list(self._futures)
        if not futures:
            return results
        try:
            iterator = as_completed(futures, timeout=timeout_seconds)
            for future in iterator:
                results.append(self._finalize_future_result(future))
        except FuturesTimeoutError:
            # Attach whatever completed just before timeout; mark the rest.
            pass

        for future in list(self._futures):
            if future.done():
                results.append(self._finalize_future_result(future))
            elif cancel_unfinished:
                results.append(
                    self._finalize_unfinished_future(
                        future,
                        reason="final_drain_timeout",
                        cancel=True,
                    )
                )
        return results

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        try:
            self._provider_executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            self._provider_executor.shutdown(wait=wait)
        try:
            self._background_executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        except TypeError:
            self._background_executor.shutdown(wait=wait)


def attach_background_results_to_transcript(
    transcript: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    *,
    timing_tracker: Dict[str, Any] = None,
    attach_turn: int = None,
    session_id: str = "",
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
        "advisory_jobs": 0,
        "combined_background_llm_jobs": 0,
        "advisory_candidates_ingested": 0,
        "background_job_seconds": 0.0,
        "deferred_narration_sources": {},
        "deferred_narration_provider_present": 0,
        "deferred_narration_provider_missing": 0,
        "deferred_narration_payload_errors": {},
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
            payload = _safe_dict(result.get("narration_payload"))
            diagnostics = _safe_dict(result.get("diagnostics"))
            source = _safe_str(payload.get("source")) or "unknown"
            summary["deferred_narration_sources"][source] = (
                int(summary["deferred_narration_sources"].get(source) or 0) + 1
            )
            provider_shape = _safe_dict(diagnostics.get("provider_shape"))
            if provider_shape.get("present"):
                summary["deferred_narration_provider_present"] += 1
            else:
                summary["deferred_narration_provider_missing"] += 1
            payload_error = (
                _safe_str(payload.get("error"))
                or _safe_str(payload.get("original_error"))
                or _safe_str(diagnostics.get("payload_error"))
                or _safe_str(diagnostics.get("payload_original_error"))
            )
            if payload_error:
                summary["deferred_narration_payload_errors"][payload_error] = (
                    int(summary["deferred_narration_payload_errors"].get(payload_error) or 0) + 1
                )
            row["deferred_narration_result"] = result
            row["narration_status"] = result.get("narration_status")
            row["deferred_narration_source"] = _safe_str(payload.get("source"))
            row["deferred_narration_diagnostics"] = diagnostics
            if result.get("ok") and result.get("narration"):
                # Do not overwrite row["turn_result"]. That object represents
                # the blocking/manual runtime result and is used to diagnose
                # whether deferred mode really avoided blocking provider
                # narration. Store background narration separately.
                row["resolved_narration"] = result.get("narration")
                row["resolved_narration_payload"] = result.get("narration_payload") or {}
                row["narration"] = result.get("narration")
        elif result.get("kind") == "checkpoint":
            summary["checkpoint_jobs"] += 1
            row["save_load_checkpoint"] = result
        elif result.get("kind") == "deferred_advisory":
            summary["advisory_jobs"] += 1
            row["deferred_advisory_result"] = result
            row["deferred_advisory_status"] = "ready" if result.get("ok") else "error"
            if result.get("ok"):
                runtime_state = _row_runtime_state(row)
                row["deferred_advisory_ingest_result"] = ingest_deferred_advisory_candidates(
                    runtime_state=runtime_state,
                    candidates=result.get("candidates") if isinstance(result.get("candidates"), list) else [],
                    turn_index=int(result.get("turn_index") or row.get("turn_index") or 0),
                    source=_safe_str(result.get("source")) or "deferred_advisory",
                )
        elif result.get("kind") == "combined_background_llm":
            summary["combined_background_llm_jobs"] += 1
            # Use timing-aware attachment if tracker provided
            if timing_tracker and attach_turn is not None:
                from tests.rpg.autoplay_llm_campaign import (
                    _attach_completed_background_job_to_record,
                )
                attached = _attach_completed_background_job_to_record(
                    record=row,
                    job_id=_safe_str(
                        row.get("combined_background_llm_job_id")
                        or row.get("background_llm_job_id")
                        or row.get("combined_background_job_id")
                        or f"combined_background_llm:{session_id}:{row.get('turn_index')}"
                    ),
                    result=result,
                    attach_turn=attach_turn,
                    phase="final",
                    timing_tracker=timing_tracker,
                )
                if attached:
                    print(
                        f"Attaching combined background LLM result for turn {row.get('turn_index')} "
                        f"phase=final lag={max(0, attach_turn - int(row.get('turn_index') or 0))}"
                    )
            else:
                # Legacy path
                if not _safe_dict(row.get("combined_background_llm_result")):
                    row["combined_background_llm_result"] = result
                    print(f"Attaching combined background LLM result for turn {turn_index}")

                    # Attach narration in the same slots used by split narration jobs.
                    row["deferred_narration_result"] = {
                        "ok": result.get("ok"),
                        "kind": "deferred_narration",
                        "session_id": result.get("session_id"),
                        "turn_index": result.get("turn_index"),
                        "narration_status": "ready" if result.get("ok") else "error",
                        "narration": result.get("narration"),
                        "npc": result.get("npc") or {},
                        "narration_payload": result.get("narration_payload") or {},
                        "diagnostics": result.get("diagnostics") or {},
                        "worker_ms": result.get("worker_ms"),
                        "queue_timing": result.get("queue_timing") or {},
                    }
                    row["narration_status"] = "ready" if result.get("ok") else "error"
                    if result.get("ok") and result.get("narration"):
                        row["resolved_narration"] = result.get("narration")
                        row["resolved_narration_payload"] = result.get("narration_payload") or {}
                        row["narration"] = result.get("narration")

                    # Attach advisory in the same slots used by split advisory jobs.
                    row["deferred_advisory_result"] = {
                        "ok": result.get("ok"),
                        "kind": "deferred_advisory",
                        "session_id": result.get("session_id"),
                        "turn_index": result.get("turn_index"),
                        "source": result.get("source"),
                        "candidate_count": result.get("candidate_count"),
                        "candidates": result.get("candidates") or [],
                        "summary": result.get("advisory_summary") or {},
                        "diagnostics": result.get("diagnostics") or {},
                        "worker_ms": result.get("worker_ms"),
                        "queue_timing": result.get("queue_timing") or {},
                    }
                    row["deferred_advisory_status"] = "ready" if result.get("ok") else "error"
                    if result.get("ok"):
                        runtime_state = _row_runtime_state(row)
                        row["deferred_advisory_ingest_result"] = ingest_deferred_advisory_candidates(
                            runtime_state=runtime_state,
                            candidates=result.get("candidates") if isinstance(result.get("candidates"), list) else [],
                            turn_index=int(result.get("turn_index") or row.get("turn_index") or 0),
                            source=_safe_str(result.get("source")) or "combined_background_llm",
                        )

    provider_jobs = [
        result
        for result in results
        if result.get("kind") in {"deferred_narration", "deferred_advisory", "combined_background_llm"}
    ]
    summary["advisory_candidates_ingested"] = sum(
        int(_safe_dict(row.get("deferred_advisory_ingest_result")).get("added") or 0)
        for row in transcript
        if isinstance(row, dict)
    )
    summary["provider_queue_summary"] = _queue_summary(provider_jobs)
    summary["provider_queue_by_kind"] = {
        kind: _queue_summary([result for result in provider_jobs if result.get("kind") == kind])
        for kind in ("deferred_narration", "deferred_advisory", "combined_background_llm")
    }

    summary["background_job_seconds"] = round(summary["background_job_seconds"], 3)
    return summary
__all__ = [name for name in globals() if not name.startswith("__")]
