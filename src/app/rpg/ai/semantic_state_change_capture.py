from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from app.providers.base import ChatMessage
from app.rpg.session import runtime as runtime_mod


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_actor_states_from_simulation(simulation_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Keep capture actor extraction aligned with runtime validator source of truth.
    return runtime_mod._safe_actor_states(simulation_state)


def _infer_actor_from_text(proposal: Dict[str, Any], simulation_state: Dict[str, Any]) -> str:
    proposal = _safe_dict(proposal)
    simulation_state = _safe_dict(simulation_state)
    text = " ".join([
        _safe_str(proposal.get("summary")),
        _safe_str(proposal.get("beat_summary")),
    ]).lower()
    npc_index = _safe_dict(simulation_state.get("npc_index"))
    for npc_id, npc in npc_index.items():
        name = _safe_str(_safe_dict(npc).get("name")).lower()
        if name and name in text:
            return _safe_str(npc_id)
    return ""


def normalize_semantic_state_change_llm_output(
    raw_output: Any,
    simulation_state: Dict[str, Any] | None = None,
    runtime_state: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    raw_text = _normalize_provider_text(raw_output)
    text = _extract_json_payload(raw_text)
    if not text:
        return []

    try:
        data = json.loads(text)
    except Exception:
        return []

    proposals: List[Dict[str, Any]] = []
    if isinstance(data, dict) and "state_changes" in data:
        proposals = _safe_list(data.get("state_changes"))
    elif isinstance(data, dict):
        proposals = [data]
    elif isinstance(data, list):
        proposals = data
    else:
        return []

    simulation_state = _safe_dict(simulation_state)
    runtime_state = runtime_mod._ensure_semantic_pipeline_state(_safe_dict(runtime_state))

    normalized: List[Dict[str, Any]] = []
    for proposal in proposals:
        proposal = _safe_dict(proposal)
        actor_id = _safe_str(proposal.get("actor_id"))
        semantic_action = _safe_str(proposal.get("semantic_action"))
        delta = _safe_dict(proposal.get("delta"))

        if not delta:
            if semantic_action == "rest":
                delta = {"activity": "resting", "engagement": "inactive"}
            elif semantic_action == "argue":
                delta = {"activity": "arguing", "engagement": "active"}
            elif semantic_action == "observe":
                delta = {"activity": "observing", "engagement": "focused"}

        normalized_proposal = {
                "proposal_id": _safe_str(proposal.get("proposal_id")),
                "actor_id": actor_id,
                "proposal_kind": _safe_str(proposal.get("proposal_kind")) or "state_delta",
                "semantic_action": semantic_action,
                "target_id": _safe_str(proposal.get("target_id")),
                "target_location_id": _safe_str(proposal.get("target_location_id")),
                "summary": _safe_str(proposal.get("summary")),
                "beat_summary": _safe_str(proposal.get("beat_summary")),
                "priority": int(proposal.get("priority") or 50),
                "delta": delta,
                "tags": _safe_list(proposal.get("tags")),
        }
        normalized_proposal["proposal_id"] = (
            _safe_str(normalized_proposal.get("proposal_id"))
            or runtime_mod._stable_semantic_state_change_proposal_id(
                normalized_proposal,
                simulation_state,
                runtime_state,
            )
        )
        normalized.append(
            normalized_proposal
        )
    return normalized


def _resolve_runtime_actor_id(actor_id, simulation_state, runtime_state):
    actor_id = _safe_str(actor_id)

    simulation_state = _safe_dict(simulation_state)

    # 🔥 canonical source of truth
    npc_index = _safe_dict(simulation_state.get("npc_index"))

    if actor_id in npc_index:
        return actor_id  # <-- THIS is the correct identity space

    # fallback: try to find matching npc key
    for npc_id, npc in npc_index.items():
        npc = _safe_dict(npc)

        if _safe_str(npc.get("id")) == actor_id:
            return _safe_str(npc_id)

        if _safe_str(npc.get("name")) == actor_id:
            return _safe_str(npc_id)

    print("SEMANTIC CAPTURE actor_id unresolved =", actor_id)
    return actor_id


def _extract_json_payload(raw_text: str) -> str:
    text = _safe_str(raw_text)
    if not text:
        return ""

    match = re.search(r"<RESPONSE>(.*?)</RESPONSE>", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1].strip()

    print("SEMANTIC CAPTURE no valid JSON found")
    return ""


def _current_authoritative_tick(simulation_state: Dict[str, Any], runtime_state: Dict[str, Any]) -> int:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = runtime_mod._ensure_semantic_pipeline_state(_safe_dict(runtime_state))
    tick = (
        _safe_int(simulation_state.get("current_tick", 0), 0)
        or _safe_int(simulation_state.get("tick", 0), 0)
        or _safe_int(runtime_state.get("tick", 0), 0)
    )
    if not tick:
        tick = _safe_int(runtime_state.get("tick", 0), 0)
    return tick


def _get_llm_provider():
    try:
        from app.shared import get_provider
        return get_provider()
    except Exception:
        return None


def _normalize_provider_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw

    if isinstance(raw, dict):
        for key in ("text", "output_text", "content", "response"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
        return str(raw)

    for attr in ("text", "content", "response"):
        value = getattr(raw, attr, None)
        if isinstance(value, str):
            return value

    return str(raw)


def should_capture_semantic_state_change_proposals(
    simulation_state: Dict[str, Any],
    runtime_state: Dict[str, Any],
) -> bool:
    simulation_state = _safe_dict(simulation_state)
    runtime_state = runtime_mod._ensure_semantic_pipeline_state(_safe_dict(runtime_state))

    # Allow low-frequency continuous behavior generation. Only suppress when
    # the queue is already meaningfully populated.
    if len(_safe_list(runtime_state.get("semantic_state_change_proposals"))) > 2:
        print("SEMANTIC CAPTURE early_false = queue_gt_2")
        return False
    if _safe_list(runtime_state.get("recorded_semantic_llm_proposals")):
        print("SEMANTIC CAPTURE early_false = recorded_already_present")
        return False

    # Interactions are now allowed. They are an especially important source of
    # activity proposals because NPCs should not appear idle during them.
    # We still require at least one actor state and enforce cooldown below.

    actor_states = runtime_mod._safe_actor_states(simulation_state)

    if not actor_states:
        actor_states = _extract_actor_states_from_simulation(simulation_state)

    if not actor_states:
        print("SEMANTIC CAPTURE early_false = no_actor_states")
        print("SEMANTIC CAPTURE npc_index keys =", list(_safe_dict(simulation_state.get("npc_index")).keys())[:5])
        return False

    tick = _current_authoritative_tick(simulation_state, runtime_state)
    last_tick = _safe_int(runtime_state.get("last_semantic_llm_tick", -999999), -999999)
    cooldown_ok = (tick - last_tick) >= runtime_mod._SEMANTIC_LLM_PROPOSAL_COOLDOWN_TICKS

    print("SEMANTIC CAPTURE sim.tick =", simulation_state.get("tick"))
    print("SEMANTIC CAPTURE sim.current_tick =", simulation_state.get("current_tick"))
    print("SEMANTIC CAPTURE runtime.tick =", runtime_state.get("tick"))
    print("SEMANTIC CAPTURE resolved tick =", tick)
    print("SEMANTIC CAPTURE last_tick =", last_tick)
    print("SEMANTIC CAPTURE actor_count =", len(actor_states))
    print("SEMANTIC CAPTURE interaction_count =", len(runtime_mod._normalize_active_interactions(simulation_state, runtime_state)))
    print("SEMANTIC CAPTURE queued =", len(runtime_state.get("semantic_state_change_proposals") or []))
    print("SEMANTIC CAPTURE recorded =", len(runtime_state.get("recorded_semantic_llm_proposals") or []))
    print("SEMANTIC CAPTURE cooldown_ok =", cooldown_ok)

    if not cooldown_ok:
        print("SEMANTIC CAPTURE early_false = cooldown_closed")
        return False

    print("SEMANTIC CAPTURE should_capture = True")
    return True


def capture_semantic_state_change_proposals_for_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upstream recorded LLM proposal capture.

    This function is intentionally outside the authoritative idle reducer.
    It performs the live LLM call, records prompt/raw output/normalized proposals
    into runtime_state, and returns the updated session.
    """
    print("SEMANTIC CAPTURE entered")
    session = _safe_dict(session)
    simulation_state = _safe_dict(session.get("simulation_state"))
    runtime_state = runtime_mod._ensure_semantic_pipeline_state(_safe_dict(session.get("runtime_state")))
    print("SEMANTIC CAPTURE session has npc_states =", bool((simulation_state.get("npc_states") or [])))
    print("SEMANTIC CAPTURE session has actor_states =", bool((simulation_state.get("actor_states") or [])))
    print("SEMANTIC CAPTURE last_semantic_llm_tick =", runtime_state.get("last_semantic_llm_tick"))
    tick = _current_authoritative_tick(simulation_state, runtime_state)

    actor_states = runtime_mod._safe_actor_states(simulation_state)
    if not actor_states:
        actor_states = _extract_actor_states_from_simulation(simulation_state)
    simulation_state["actor_states"] = actor_states

    if not should_capture_semantic_state_change_proposals(simulation_state, runtime_state):
        print("SEMANTIC CAPTURE early_exit = should_capture_false")
        session["runtime_state"] = runtime_state
        return session

    provider = _get_llm_provider()
    print("SEMANTIC CAPTURE provider =", type(provider).__name__ if provider else None)
    if provider is None:
        print("SEMANTIC CAPTURE early_exit = provider_none")
        session["runtime_state"] = runtime_state
        return session

    prompt = runtime_mod.preview_semantic_state_change_prompt(simulation_state, runtime_state)
    print("SEMANTIC CAPTURE prompt_present =", bool(prompt))
    raw_output: Any = ""

    try:
        if hasattr(provider, "chat_completion"):
            print("SEMANTIC CAPTURE provider method = chat_completion")
            messages = [ChatMessage(role="user", content=prompt)]
            raw_output = provider.chat_completion(messages=messages, stream=False)
        elif hasattr(provider, "complete"):
            print("SEMANTIC CAPTURE provider method = complete")
            raw_output = provider.complete(prompt=prompt)
        elif hasattr(provider, "generate"):
            print("SEMANTIC CAPTURE provider method = generate")
            raw_output = provider.generate(prompt=prompt)
        else:
            methods = [
                name for name in dir(provider)
                if not name.startswith("_") and callable(getattr(provider, name, None))
            ]
            print("SEMANTIC CAPTURE provider public methods =", methods)
            print("SEMANTIC CAPTURE early_exit = provider_shape_unsupported")
            session["runtime_state"] = runtime_state
            return session
    except Exception as exc:
        print("SEMANTIC CAPTURE early_exit = provider_exception", repr(exc))
        session["runtime_state"] = runtime_state
        return session
    except Exception as exc:
        print("SEMANTIC CAPTURE early_exit = provider_exception", repr(exc))
        session["runtime_state"] = runtime_state
        return session

    print("SEMANTIC CAPTURE raw_output =", repr(raw_output)[:1000])

    normalized = normalize_semantic_state_change_llm_output(
        raw_output,
        simulation_state=simulation_state,
        runtime_state=runtime_state,
    )
    print("SEMANTIC CAPTURE normalized_count =", len(normalized))
    print("SEMANTIC CAPTURE normalized =", normalized[:3])

    # Force non-empty delta
    for p in normalized:
        delta = _safe_dict(p.get("delta"))

        if not delta:
            print("SEMANTIC CAPTURE fixing empty delta")

            action = _safe_str(p.get("semantic_action"))

            if action == "rest":
                delta = {
                    "activity": "resting",
                    "engagement": "inactive"
                }
            elif action == "argue":
                delta = {
                    "activity": "arguing",
                    "engagement": "active"
                }
            elif action == "observe":
                delta = {
                    "activity": "observing",
                    "engagement": "focused"
                }
            else:
                delta = {
                    "activity": "engaged",
                    "engagement": "active"
                }

            p["delta"] = delta

    # Apply runtime actor-ID resolver
    for p in normalized:
        actor_id = _safe_str(p.get("actor_id"))
        if actor_id:
            p["actor_id"] = _resolve_runtime_actor_id(actor_id, simulation_state, runtime_state)

    # Fix actor mismatch
    for p in normalized:
        actor_id = _safe_str(p.get("actor_id"))

        inferred = _infer_actor_from_text(p, simulation_state)

        # 🔥 FIX: override if mismatch or missing
        if inferred and inferred != actor_id:
            print("SEMANTIC CAPTURE actor corrected:", actor_id, "→", inferred)
            p["actor_id"] = inferred

        elif not actor_id and inferred:
            p["actor_id"] = inferred

    # Reduce passive filler when no interaction is active.
    interactions = runtime_mod._normalize_active_interactions(simulation_state, runtime_state)
    if not interactions:
        for p in normalized:
            action = _safe_str(p.get("semantic_action"))
            if action in ("continue_activity", "", "observe", "scan_room"):
                p["semantic_action"] = "observe"
                delta = _safe_dict(p.get("delta"))
                if not _safe_str(delta.get("activity")) or _safe_str(delta.get("activity")) == "active":
                    delta["activity"] = "observing"
                if not _safe_str(delta.get("engagement")) or _safe_str(delta.get("engagement")) == "ongoing":
                    delta["engagement"] = "focused"
                p["delta"] = delta

    # Deterministic fallback if normalization returns empty
    if not normalized:
        actor_states = runtime_mod._safe_actor_states(simulation_state)
        if not actor_states:
            actor_states = _extract_actor_states_from_simulation(simulation_state)

        if actor_states:
            actor = actor_states[0]
            raw_actor_id = str(actor.get("id") or "").strip()
            resolved_actor_id = _resolve_runtime_actor_id(raw_actor_id, simulation_state, runtime_state)
            actor_name = str(actor.get("name") or "Someone").strip()
            if resolved_actor_id:
                normalized = [{
                    "proposal_id": f"fallback_{resolved_actor_id}_{tick}",
                    "actor_id": resolved_actor_id,
                    "proposal_kind": "state_delta",
                    "semantic_action": "observe",
                    "delta": {
                        "activity": str(actor.get("activity") or "observing"),
                        "engagement": str(actor.get("engagement") or "focused"),
                    },
                    "beat_summary": f"{actor_name} watches the area carefully.",
                    "priority": 5,
                    "tags": ["fallback", "activity"],
                }]
                print("SEMANTIC CAPTURE fallback_normalized =", normalized)

    # Reduce fallback dominance
    recent = runtime_state.get("recent_semantic_actions", [])

    # Add action variety boost
    import random

    interactions = runtime_mod._normalize_active_interactions(simulation_state, runtime_state)

    if not interactions:
        for p in normalized:
            if p.get("semantic_action") in ("continue_activity", ""):
                p["semantic_action"] = random.choice([
                    "observe",
                    "adjust_position",
                    "scan_room",
                    "react_environment",
                    "consider_options"
                ])

    for p in normalized:
        if p.get("semantic_action") == "continue_activity":
            if recent and recent[-1] == "continue_activity":
                p["priority"] = 1  # almost ignore

    # Verify interaction actor filtering
    interactions = runtime_mod._normalize_active_interactions(simulation_state, runtime_state)
    if interactions:
        allowed = set()
        for row in interactions:
            for actor_id in row.get("participants") or []:
                actor_id = str(actor_id).strip()
                if actor_id:
                    allowed.add(actor_id)

        if allowed:
            normalized = [
                p for p in normalized
                if str((p or {}).get("actor_id") or "").strip() in allowed
            ]

    print("SEMANTIC CAPTURE remapped proposals =", normalized[:3])
    print("SEMANTIC CAPTURE final actor_ids =", [p.get("actor_id") for p in normalized])
    print("SEMANTIC CAPTURE npc_index_keys =", list(_safe_dict(simulation_state.get("npc_index")).keys())[:5])

    runtime_state = runtime_mod.record_semantic_llm_capture(
        runtime_state,
        simulation_state,
        prompt=prompt,
        raw_output=_normalize_provider_text(raw_output),
        proposals=normalized,
        tick=tick,
    )
    session["runtime_state"] = runtime_state
    return session