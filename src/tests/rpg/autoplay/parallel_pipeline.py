from __future__ import annotations

import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from typing import Any, Dict, List

from app.rpg.narration.runtime_narration_contract import build_runtime_narration_payload
try:
    from app.providers.base import ChatMessage
except Exception:
    ChatMessage = None
from app.rpg.advisory.candidates import (
    advisory_candidate_summary,
    build_deterministic_advisory_candidates,
    normalize_advisory_candidates,
    stable_json_for_prompt,
)
from tests.rpg.autoplay.checkpoints import validate_save_load_checkpoint
from tests.rpg.autoplay.performance import elapsed_ms, now_perf
from tests.rpg.autoplay.progress import state_digest


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _provider_shape(provider: Any) -> Dict[str, Any]:
    if provider is None:
        return {"present": False}
    return {
        "present": True,
        "type": type(provider).__name__,
        "module": getattr(type(provider), "__module__", ""),
        "has_chat_completion": callable(getattr(provider, "chat_completion", None)),
        "has_complete": callable(getattr(provider, "complete", None)),
        "provider_name": getattr(provider, "provider_name", ""),
        "provider_display_name": getattr(provider, "provider_display_name", ""),
    }


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
    wall_started = time.perf_counter()
    before_digest = state_digest(_safe_dict(simulation_state))
    frozen_state = freeze_snapshot(_safe_dict(simulation_state))
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "state_keys": sorted(list(frozen_state.keys()))[:80],
    }
    try:
        build_started = now_perf()
        payload = build_runtime_narration_payload(
            provider=provider,
            player_action=player_action,
            simulation_state=frozen_state,
            turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
            prefer_provider=bool(prefer_provider),
        )
        diagnostics["build_runtime_narration_payload_ms"] = elapsed_ms(build_started)
        diagnostics["payload_source"] = payload.get("source") if isinstance(payload, dict) else ""
        diagnostics["payload_has_narration"] = bool(_safe_str(_safe_dict(payload).get("narration")))
        diagnostics["payload_error"] = _safe_str(_safe_dict(payload).get("error"))
        diagnostics["payload_original_error"] = _safe_str(_safe_dict(payload).get("original_error"))
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
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "worker_wall_seconds": round(time.perf_counter() - wall_started, 3),
            "state_digest_before": before_digest,
            "state_digest_after": after_digest,
            "mutated_authoritative_snapshot": before_digest != after_digest,
        }
    except Exception as exc:
        diagnostics["exception"] = f"{type(exc).__name__}: {exc}"
        return {
            "ok": False,
            "kind": "deferred_narration",
            "session_id": session_id,
            "turn_index": turn_index,
            "narration_status": "error",
            "narration_job_id": f"narration:{session_id}:{turn_index}",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
            "worker_wall_seconds": round(time.perf_counter() - wall_started, 3),
        }


def _provider_text_from_response(response: Any) -> str:
    for attr in ("content", "text", "message"):
        value = getattr(response, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(response, dict):
        for key in ("content", "text", "message"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_json_object_from_text(text: str) -> Dict[str, Any]:
    """Extract a JSON object from raw provider text.

    Local models often return ```json fences or a short preamble before JSON.
    Advisory extraction is background-only, so be permissive and normalize the
    first valid object we can find.
    """
    import json
    import re

    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty_provider_text")

    cleaned = text.strip()

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find("{")
    if start < 0:
        raise ValueError("no_json_object_start")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : index + 1])

    raise ValueError("unterminated_json_object")


def _provider_messages(messages: List[Dict[str, str]]) -> List[Any]:
    if ChatMessage is None:
        return messages
    converted: List[Any] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        try:
            converted.append(ChatMessage(role=role, content=content))
        except TypeError:
            converted.append(ChatMessage(role, content))
    return converted


def _build_provider_advisory_payload(
    *,
    provider: Any,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
) -> Dict[str, Any]:
    if provider is None or not callable(getattr(provider, "chat_completion", None)):
        return {"ok": False, "error": "provider_missing_or_unsupported"}

    messages = [
        {
            "role": "system",
            "content": (
                "You are an RPG advisory extractor. Return JSON only. "
                "You may suggest candidates, but you must not assert authoritative outcomes. "
                "Do not grant items, currency, quest completion, damage, travel, or rewards. "
                "Return one JSON object and no markdown fences, no prose, no commentary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Extract advisory candidates from this turn.\n\n"
                f"PLAYER_INPUT:\n{player_action}\n\n"
                f"TURN_CONTRACT_JSON:\n{stable_json_for_prompt(turn_contract)}\n\n"
                f"FAST_SEMANTIC_JSON:\n{stable_json_for_prompt(semantic_action_record)}\n\n"
                "Return JSON with optional arrays: semantic_intent_candidates, "
                "relationship_delta_candidates, memory_candidates, world_signal_candidates, "
                "future_hook_candidates.\n\n"
                "Example shape:\n"
                "{\n"
                '  "semantic_intent_candidates": [\n'
                '    {"intent": "inspect", "summary": "The player studies the room.", "confidence": 0.7}\n'
                "  ],\n"
                '  "future_hook_candidates": [\n'
                '    {"summary": "An NPC may respond to the player noticing suspicious details."}\n'
                "  ]\n"
                "}"
            ),
        },
    ]

    provider_messages = _provider_messages(messages)
    try:
        response = provider.chat_completion(messages=provider_messages, stream=False)
    except TypeError:
        response = provider.chat_completion(provider_messages, stream=False)

    content = _provider_text_from_response(response)
    if not content:
        return {"ok": False, "error": "provider_empty_advisory_response"}

    try:
        parsed = _extract_json_object_from_text(content)
        if isinstance(parsed, dict):
            parsed["ok"] = True
            return parsed
        return {"ok": False, "error": "provider_advisory_json_not_object", "raw": content[:1000]}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"provider_advisory_json_parse_error:{type(exc).__name__}: {exc}",
            "raw": content[:1000],
        }


def _deferred_advisory_job(
    *,
    provider: Any,
    session_id: str,
    turn_index: int,
    player_action: str,
    simulation_state: Dict[str, Any],
    turn_contract: Dict[str, Any],
    semantic_action_record: Dict[str, Any],
    prefer_provider: bool,
) -> Dict[str, Any]:
    started = now_perf()
    diagnostics: Dict[str, Any] = {
        "prefer_provider": bool(prefer_provider),
        "provider_shape": _provider_shape(provider),
        "turn_contract_keys": sorted(list(_safe_dict(turn_contract).keys())),
        "semantic_keys": sorted(list(_safe_dict(semantic_action_record).keys())),
    }
    try:
        payload: Dict[str, Any] = {}
        source = "deterministic_deferred_advisory"
        if prefer_provider and provider is not None:
            provider_started = now_perf()
            payload = _build_provider_advisory_payload(
                provider=provider,
                player_action=player_action,
                simulation_state=freeze_snapshot(_safe_dict(simulation_state)),
                turn_contract=freeze_snapshot(_safe_dict(turn_contract)),
                semantic_action_record=freeze_snapshot(_safe_dict(semantic_action_record)),
            )
            diagnostics["provider_advisory_ms"] = elapsed_ms(provider_started)
            diagnostics["provider_payload_error"] = _safe_str(payload.get("error"))
            if payload.get("ok"):
                source = "provider_deferred_advisory"
            else:
                source = "deterministic_deferred_advisory_fallback"

        if source == "provider_deferred_advisory":
            candidates = normalize_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                payload=_safe_dict(payload),
            )
        else:
            candidates = build_deterministic_advisory_candidates(
                session_id=session_id,
                turn_index=turn_index,
                player_input=player_action,
                turn_contract=_safe_dict(turn_contract),
                semantic_action_record=_safe_dict(semantic_action_record),
            )

        return {
            "ok": True,
            "kind": "deferred_advisory",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": source,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "summary": advisory_candidate_summary(candidates),
            "diagnostics": diagnostics,
            "worker_ms": elapsed_ms(started),
        }
    except Exception as exc:
        return {
            "ok": False,
            "kind": "deferred_advisory",
            "session_id": session_id,
            "turn_index": turn_index,
            "source": "deferred_advisory_error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "diagnostics": diagnostics,
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
        future = self._provider_executor.submit(
            _deferred_advisory_job,
            provider=provider,
            session_id=session_id,
            turn_index=turn_index,
            player_action=player_action,
            simulation_state=freeze_snapshot(simulation_state),
            turn_contract=freeze_snapshot(turn_contract),
            semantic_action_record=freeze_snapshot(semantic_action_record),
            prefer_provider=prefer_provider,
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
        "advisory_jobs": 0,
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

    summary["background_job_seconds"] = round(summary["background_job_seconds"], 3)
    return summary