from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Tuple

from tests.rpg.autoplay.executable_actions import normalize_command_label_action


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _nested_dict(root: Dict[str, Any], *path: str) -> Dict[str, Any]:
    value: Any = root
    for key in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(key)
    return value if isinstance(value, dict) else {}


def _nested_value(root: Dict[str, Any], *path: str) -> Any:
    value: Any = root
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _normalize_semantic_action_name(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    return text.lower()


def _normalize_semantic_target_name(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    if text.startswith("npc:") and len(text) > 4:
        return text[4:]
    return text


def _semantic_candidate_from_mapping(
    mapping: Dict[str, Any],
    *,
    source: str,
) -> Dict[str, Any]:
    mapping = _safe_dict(mapping)
    if not mapping:
        return {}

    semantic_action = _normalize_semantic_action_name(
        mapping.get("semantic_action")
        or mapping.get("action_type")
        or mapping.get("action")
        or mapping.get("type")
        or mapping.get("kind")
        or mapping.get("name")
    )
    target = _normalize_semantic_target_name(
        mapping.get("semantic_target")
        or mapping.get("target_name")
        or mapping.get("target")
        or mapping.get("target_id")
        or mapping.get("object")
        or mapping.get("object_id")
        or mapping.get("normalized_target")
    )

    if not semantic_action and not target:
        return {}

    if not semantic_action:
        semantic_action = "unknown"
    if not target:
        target = "unknown"

    return {
        "ok": bool(semantic_action and semantic_action != "unknown"),
        "semantic_action": semantic_action,
        "target": target,
        "pair": f"{semantic_action}:{target}",
        "source": source,
        "raw": mapping,
    }


def canonical_semantic_pair_from_turn(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract canonical semantic action/target pair from an autoplay row.

    The autoplay/manual harness stores semantic information in several shapes.
    Action diversity already finds these pairs, but anti-loop previously only
    checked shallow row fields and therefore saw unknown:unknown.

    Prefer explicit/nested turn-contract semantic metadata, then fall back to
    existing canonical extractors and shallow compatibility fields.
    """
    row = row if isinstance(row, dict) else {}

    turn_contract = _safe_dict(row.get("turn_contract"))
    turn_result = _safe_dict(row.get("turn_result") or row.get("result"))

    candidate_mappings: List[Tuple[str, Dict[str, Any]]] = [
        ("row.semantic_action_v2", _safe_dict(row.get("semantic_action_v2"))),
        ("row.semantic_action_record", _safe_dict(row.get("semantic_action_record"))),
        (
            "row.turn_contract.action.metadata.semantic_action",
            _nested_dict(turn_contract, "action", "metadata", "semantic_action"),
        ),
        (
            "row.turn_contract.action.semantic_action",
            _nested_dict(turn_contract, "action", "semantic_action"),
        ),
        ("row.turn_contract.action", _nested_dict(turn_contract, "action")),
        (
            "row.turn_contract.resolved_action.semantic_action",
            _nested_dict(turn_contract, "resolved_action", "semantic_action"),
        ),
        ("row.turn_contract.resolved_action", _nested_dict(turn_contract, "resolved_action")),
        (
            "row.turn_contract.resolved_result.semantic_action",
            _nested_dict(turn_contract, "resolved_result", "semantic_action"),
        ),
        ("row.turn_contract.resolved_result", _nested_dict(turn_contract, "resolved_result")),
        (
            "row.turn_contract.metadata.semantic_action",
            _nested_dict(turn_contract, "metadata", "semantic_action"),
        ),
        ("row.turn_contract", turn_contract),
        ("row.turn_result.semantic_action_v2", _safe_dict(turn_result.get("semantic_action_v2"))),
        (
            "row.turn_result.turn_contract.action.metadata.semantic_action",
            _nested_dict(turn_result, "turn_contract", "action", "metadata", "semantic_action"),
        ),
        (
            "row.result.turn_contract.action.metadata.semantic_action",
            _nested_dict(turn_result, "turn_contract", "action", "metadata", "semantic_action"),
        ),
    ]

    for source, mapping in candidate_mappings:
        candidate = _semantic_candidate_from_mapping(mapping, source=source)
        if candidate and (
            candidate.get("semantic_action") != "unknown"
            or candidate.get("target") != "unknown"
        ):
            return candidate

    # Compatibility path: use existing private/public extractor if present.
    # This is intentionally after explicit nested turn-contract metadata because
    # some older extractors return partial/unknown data for current rows.
    for name in (
        "_extract_semantic_action_from_turn",
        "extract_semantic_action_from_turn",
        "_extract_semantic_action",
        "extract_semantic_action",
        "_semantic_action_from_row",
    ):
        fn = globals().get(name)
        if not callable(fn):
            continue
        try:
            value = fn(row)
        except TypeError:
            try:
                value = fn(turn=row)
            except Exception:
                value = {}
        except Exception:
            value = {}
        candidate = _semantic_candidate_from_mapping(
            _safe_dict(value),
            source=f"extractor.{name}",
        )
        if candidate and (
            candidate.get("semantic_action") != "unknown"
            or candidate.get("target") != "unknown"
        ):
            return candidate

    # Shallow legacy fallback.
    shallow_candidate = _semantic_candidate_from_mapping(
        {
            "semantic_action": (
                row.get("semantic_action")
                or row.get("semantic_action_type")
                or row.get("action_type")
                or row.get("action")
            ),
            "target": (
                row.get("semantic_target")
                or row.get("target")
                or row.get("target_name")
                or row.get("target_id")
            ),
        },
        source="row.shallow",
    )
    if shallow_candidate:
        return shallow_candidate

    # Last-resort deterministic classifier from selected/player action text.
    action_text = normalize_command_label_action(_safe_str(
        row.get("selected_player_action")
        or row.get("player_action")
        or row.get("player_input")
        or row.get("input")
    ))
    if action_text:
        lower = action_text.lower()
        target = "unknown"
        for name in ("bran", "silas", "cloaked traveler", "traveler", "patron", "innkeeper", "bartender", "side door", "street", "road", "inn"):
            if name in lower:
                if name in ("bran", "innkeeper", "bartender"):
                    target = "Bran"
                elif name == "traveler":
                    target = "Cloaked Traveler"
                elif name in ("side door", "street"):
                    target = "tavern_exit"
                elif name == "road":
                    target = "road"
                else:
                    target = name.title() if name != "inn" else "inn"
                break

        if (
            ("ask" in lower and "bran" in lower and ("saw" in lower or "personally saw" in lower) and "cloaked traveler" in lower)
            or ("where" in lower and ("witness" in lower or "cloaked traveler" in lower or "side door" in lower))
        ):
            semantic_action = "ask_witness_lead"
            if target == "unknown":
                target = "Bran"
        elif "report" in lower and ("witness" in lower or "cloaked traveler" in lower or "trail" in lower):
            semantic_action = "report_witness_findings"
            if target == "unknown":
                target = "Bran"
        elif any(term in lower for term in ("side door", "nearby street", "boot prints", "mud", "torn cloth", "hurried exit")):
            semantic_action = "inspect_witness_trail"
            target = "tavern_exit"
        elif any(term in lower for term in ("follow the road", "road outside", "fresh tracks", "follow the trail", "bandit road trail")):
            semantic_action = "follow_witness_trail"
            target = "road"
        elif any(term in lower for term in ("rent", "room", "lodging", "bed")):
            semantic_action = "rent_room"
            if target == "unknown":
                target = "inn"
        elif any(term in lower for term in ("buy", "pay", "order", "drink", "meal")):
            semantic_action = "service_inquiry"
        elif any(term in lower for term in ("ask", "question", "inquire", "press")):
            semantic_action = "service_inquiry" if target == "Bran" else "ask"
        elif any(term in lower for term in ("observe", "watch", "listen", "wait", "scan", "look")):
            semantic_action = "observe"
        elif any(term in lower for term in ("leave", "travel", "go to", "head outside", "step outside")):
            semantic_action = "travel"
        elif any(term in lower for term in ("inspect", "examine", "search", "check")):
            semantic_action = "inspect"
        else:
            semantic_action = "unknown"

        return {
            "ok": semantic_action != "unknown",
            "semantic_action": semantic_action,
            "target": target,
            "pair": f"{semantic_action}:{target}",
            "source": "player_action_text_fallback",
            "raw": {"text": action_text},
        }

    return {
        "ok": False,
        "semantic_action": "unknown",
        "target": "unknown",
        "pair": "unknown:unknown",
        "source": "canonical_semantic_pair_from_turn.none",
        "raw": {},
    }


def _norm_token(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    text = text.replace("-", "_").replace(" ", "_").strip("_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.lower()


def _clean_target_label(value: Any) -> str:
    text = _safe_str(value).strip()
    if not text:
        return ""
    # Normalize common id/display forms.
    if text.lower().startswith("npc:"):
        text = text.split(":", 1)[1].strip()
    if "(" in text and ")" in text:
        text = text.split("(", 1)[0].strip()
    text = text.strip(" .,:;[]{}\"'")
    return text


def _present_npc_aliases(row: Dict[str, Any]) -> Dict[str, str]:
    """Return lowercase aliases -> canonical NPC display id/name."""
    row = _safe_dict(row)
    aliases: Dict[str, str] = {}

    def add(name: Any, canonical: Any = "") -> None:
        raw = _clean_target_label(name)
        if not raw:
            return
        canon = _clean_target_label(canonical) or raw
        aliases[raw.lower()] = canon
        aliases[raw.replace(" ", "_").lower()] = canon
        aliases[f"npc:{raw}".lower()] = canon
        aliases[f"npc:{raw.replace(' ', '_')}".lower()] = canon

    state_candidates = [
        _safe_dict(row.get("simulation_state")),
        _safe_dict(row.get("final_authoritative_state")),
        _safe_dict(_safe_dict(row.get("turn_result")).get("simulation_state")),
        _safe_dict(_safe_dict(_safe_dict(row.get("turn_result")).get("session")).get("simulation_state")),
    ]
    runtime_state = _safe_dict(row.get("runtime_state"))
    loaded_profiles = _safe_dict(_safe_dict(runtime_state.get("npc_evolution")).get("loaded_profiles"))
    for npc_id, profile_row in loaded_profiles.items():
        profile = _safe_dict(_safe_dict(profile_row).get("profile"))
        add(npc_id)
        add(profile.get("npc_id"), npc_id)
        add(profile.get("name"), npc_id)

    for state in state_candidates:
        scene = _safe_dict(state.get("scene"))
        for npc in _safe_list(scene.get("nearby_npcs")) + _safe_list(scene.get("present_npcs")):
            if isinstance(npc, dict):
                add(npc.get("npc_id") or npc.get("id") or npc.get("name"))
                add(npc.get("name"), npc.get("npc_id") or npc.get("id") or npc.get("name"))
                add(npc.get("role"), npc.get("npc_id") or npc.get("id") or npc.get("name"))
            else:
                add(npc)
        npcs = _safe_dict(_safe_dict(state.get("npc_progression_state")).get("npcs"))
        for npc_id, npc_any in npcs.items():
            npc = _safe_dict(npc_any)
            add(npc_id)
            add(npc.get("name"), npc_id)
            add(npc.get("role"), npc_id)

    # Useful role aliases for the tavern seed, but only when a matching NPC is present.
    for alias in ("innkeeper", "barkeep", "bartender", "tavernkeeper"):
        if alias in aliases:
            continue
        for _, canon in list(aliases.items()):
            if canon.lower() == "bran":
                aliases[alias] = canon
                break
    return aliases


def _normalize_target(value: Any, row: Dict[str, Any]) -> str:
    text = _clean_target_label(value)
    if not text:
        return ""
    aliases = _present_npc_aliases(row)
    lower = text.lower()
    if lower in aliases:
        return aliases[lower]
    lower_underscored = lower.replace(" ", "_")
    if lower_underscored in aliases:
        return aliases[lower_underscored]
    if text.lower() in {"none", "unknown", "null"}:
        return ""
    return text


def _first_value(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _turn_index(row: Dict[str, Any], fallback: int) -> int:
    try:
        return int(_safe_dict(row).get("turn_index") or fallback)
    except Exception:
        return fallback


def _player_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    selected = _safe_dict(row.get("selected_player_action"))
    return (
        _safe_str(row.get("player_action"))
        or _safe_str(row.get("player_input"))
        or _safe_str(selected.get("action"))
        or _safe_str(_safe_dict(row.get("turn_contract")).get("player_input"))
        or _safe_str(_safe_dict(row.get("turn_contract")).get("action"))
    )


def _semantic_dict_candidates(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    row = _safe_dict(row)
    contract = _safe_dict(row.get("turn_contract"))
    selected = _safe_dict(row.get("selected_player_action"))
    turn_result = _safe_dict(row.get("turn_result"))
    combined = _safe_dict(row.get("combined_background_llm_result"))
    diagnostics = _safe_dict(combined.get("diagnostics"))
    context_packet = _safe_dict(diagnostics.get("context_packet"))
    result = _safe_dict(turn_result.get("result"))

    candidates: List[Dict[str, Any]] = [
        _safe_dict(contract.get("semantic_action")),
        _safe_dict(contract.get("semantic_action_v2")),
        _safe_dict(contract.get("resolved_action")),
        _safe_dict(contract.get("action")),
        _safe_dict(row.get("semantic_action")),
        _safe_dict(row.get("semantic_action_v2")),
        _safe_dict(row.get("fast_semantic_action")),
        _safe_dict(row.get("semantic_action_record")),
        _safe_dict(row.get("background_semantic_action_record")),
        _safe_dict(selected.get("semantic_action")),
        _safe_dict(selected.get("semantic_action_v2")),
        _safe_dict(selected.get("fast_semantic_action")),
        _safe_dict(result.get("semantic_action")),
        _safe_dict(result.get("semantic_action_v2")),
        _safe_dict(result.get("resolved_action")),
        _safe_dict(combined.get("semantic_action")),
        _safe_dict(combined.get("semantic_action_v2")),
        _safe_dict(combined.get("fast_semantic_action")),
        _safe_dict(diagnostics.get("semantic_action")),
        _safe_dict(diagnostics.get("fast_semantic_action")),
        _safe_dict(context_packet.get("fast_semantic_action")),
    ]

    # Some traces store this as a row/list payload.
    trace = _safe_dict(row.get("player_agent_trace"))
    candidates.extend(
        [
            _safe_dict(trace.get("semantic_action")),
            _safe_dict(trace.get("semantic_action_v2")),
            _safe_dict(trace.get("selected_semantic_action")),
        ]
    )

    return [candidate for candidate in candidates if candidate]


def _semantic_action_from_text(action: str) -> str:
    lower = _safe_str(action).lower().strip()
    if not lower:
        return "unknown"
    # Deterministic fallback only for evaluation when structured fields are absent.
    if lower.startswith(("ask ", "question ", "inquire ", "talk ", "speak ", "tell ")):
        return "ask"
    if lower.startswith(("listen", "observe", "look", "watch", "inspect", "examine", "search")):
        return "observe"
    if lower.startswith(("go ", "travel ", "walk ", "move ", "leave ", "enter ")):
        return "travel"
    if lower.startswith(("buy ", "purchase ", "rent ", "pay ")):
        return "service"
    if lower.startswith(("attack ", "strike ", "fight ", "punch ")):
        return "combat"
    if lower.startswith(("wait", "rest", "idle")):
        return "wait"
    return "unknown"


def _target_from_text(action: str, row: Dict[str, Any]) -> str:
    lower = _safe_str(action).lower()
    aliases = _present_npc_aliases(row)
    for alias, canon in aliases.items():
        if alias and alias in lower:
            return canon
    # Common tavern role fallback, only normalized if row has Bran alias.
    if "innkeeper" in lower or "barkeep" in lower or "bartender" in lower:
        return _normalize_target("innkeeper", row)
    return ""


def _semantic_action(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    for candidate in _semantic_dict_candidates(row):
        value = _first_value(
            candidate.get("semantic_action_type"),
            candidate.get("action_type"),
            candidate.get("type"),
            candidate.get("kind"),
            candidate.get("intent"),
            candidate.get("verb"),
            candidate.get("category"),
        )
        value = _norm_token(value)
        if value and value not in {"unknown", "none", "null"}:
            return value

    selected = _safe_dict(row.get("selected_player_action"))
    value = _norm_token(
        _first_value(
            selected.get("semantic_action_type"),
            selected.get("action_type"),
            row.get("semantic_action_type"),
            row.get("action_type"),
        )
    )
    if value and value not in {"unknown", "none", "null"}:
        return value

    return _semantic_action_from_text(_player_action(row))


def _target(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    for candidate in _semantic_dict_candidates(row):
        value = _first_value(
            candidate.get("target"),
            candidate.get("target_id"),
            candidate.get("target_name"),
            candidate.get("npc_id"),
            candidate.get("object"),
            candidate.get("entity"),
        )
        normalized = _normalize_target(value, row)
        if normalized:
            return normalized

    selected = _safe_dict(row.get("selected_player_action"))
    normalized = _normalize_target(
        _first_value(
            selected.get("target"),
            selected.get("target_id"),
            selected.get("target_name"),
            row.get("target"),
            row.get("target_id"),
        ),
        row,
    )
    if normalized:
        return normalized

    return _target_from_text(_player_action(row), row)


def _result_reason(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    contract = _safe_dict(row.get("turn_contract"))
    resolved = _safe_dict(contract.get("resolved_result"))
    service = _safe_dict(contract.get("service_result"))
    turn_result = _safe_dict(row.get("turn_result"))
    return (
        _safe_str(resolved.get("reason"))
        or _safe_str(resolved.get("code"))
        or _safe_str(service.get("reason"))
        or _safe_str(turn_result.get("reason"))
        or _safe_str(turn_result.get("error"))
        or ""
    )


def _location(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    state_candidates = [
        _safe_dict(row.get("simulation_state")),
        _safe_dict(row.get("final_authoritative_state")),
        _safe_dict(_safe_dict(row.get("turn_result")).get("simulation_state")),
        _safe_dict(_safe_dict(_safe_dict(row.get("turn_result")).get("session")).get("simulation_state")),
    ]
    for state in state_candidates:
        for key in ("location", "current_location", "scene_id"):
            value = _safe_str(state.get(key))
            if value:
                return value
        scene = _safe_dict(state.get("scene"))
        value = _safe_str(scene.get("id") or scene.get("scene_id") or scene.get("title") or scene.get("name"))
        if value:
            return value
    contract = _safe_dict(row.get("turn_contract"))
    resolved = _safe_dict(contract.get("resolved_result"))
    location_state = _safe_dict(resolved.get("location_state"))
    current = _safe_dict(location_state.get("current_location"))
    return _safe_str(current.get("id") or current.get("title") or current.get("name"))


def _has_story_beat(row: Dict[str, Any]) -> bool:
    row = _safe_dict(row)
    if _safe_str(row.get("narration")):
        return True
    if _safe_dict(row.get("combined_background_llm_result")).get("narration"):
        return True
    if _safe_dict(row.get("story_hook_result")):
        return True
    if _safe_dict(row.get("progress_delta")):
        return True
    contract = _safe_dict(row.get("turn_contract"))
    if _safe_dict(contract.get("state_delta")):
        return True
    if _safe_dict(contract.get("resolved_result")).get("summary"):
        return True
    return False


def _quest_count(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    runtime = _safe_dict(row.get("runtime_state"))
    quest_progress = _safe_dict(runtime.get("quest_progress"))
    quests = _safe_dict(quest_progress.get("quests"))
    return len(quests)


def _journal_entry_count(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    runtime = _safe_dict(row.get("runtime_state"))
    journal = _safe_dict(runtime.get("player_journal"))
    return len(_safe_list(journal.get("entries")))


def _npc_signal_count(row: Dict[str, Any]) -> int:
    row = _safe_dict(row)
    runtime = _safe_dict(row.get("runtime_state"))
    evo = _safe_dict(runtime.get("npc_evolution"))
    return len(_safe_list(evo.get("signals")))


def _manual_error(row: Dict[str, Any]) -> str:
    row = _safe_dict(row)
    return (
        _safe_str(row.get("runtime_error"))
        or _safe_str(_safe_dict(row.get("manual_turn_summary")).get("error"))
        or _safe_str(_safe_dict(row.get("turn_result")).get("error"))
    )


def _is_noop_reason(reason: str) -> bool:
    lower = _safe_str(reason).lower()
    if not lower:
        return False
    return any(
        token in lower
        for token in (
            "target_not_found",
            "no_supported_semantic_action_detected",
            "unsupported_action",
            "action_unhandled",
            "no_effect",
            "no_op",
            "noop",
            "service_not_available",
        )
    )


def _max_streak(values: List[bool]) -> int:
    best = 0
    current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _repeat_streak(items: List[str]) -> Dict[str, Any]:
    best_value = ""
    best = 0
    current_value = ""
    current = 0
    for item in items:
        marker = item or "unknown"
        if marker == current_value:
            current += 1
        else:
            current_value = marker
            current = 1
        if current > best:
            best = current
            best_value = marker
    return {"value": best_value, "streak": best}


def summarize_action_diversity(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in (transcript if isinstance(transcript, list) else [])]
    actions = [_player_action(row) for row in rows]
    semantics = [_semantic_action(row) for row in rows]
    targets = [_target(row) for row in rows]
    semantic_target = [
        f"{semantic}:{target or 'none'}"
        for semantic, target in zip(semantics, targets)
    ]

    action_counter = Counter(action for action in actions if action)
    semantic_counter = Counter(semantics)
    target_counter = Counter(target for target in targets if target)
    semantic_target_counter = Counter(semantic_target)
    unknown_semantic_count = semantic_counter.get("unknown", 0)
    missing_target_count = sum(1 for target in targets if not target)

    return {
        "turns": len(rows),
        "unique_action_count": len(action_counter),
        "unique_semantic_action_count": len(semantic_counter),
        "unique_target_count": len(target_counter),
        "unique_semantic_target_count": len(semantic_target_counter),
        "unknown_semantic_count": unknown_semantic_count,
        "unknown_semantic_rate": round(unknown_semantic_count / len(rows), 4) if rows else 0.0,
        "missing_target_count": missing_target_count,
        "missing_target_rate": round(missing_target_count / len(rows), 4) if rows else 0.0,
        "top_actions": action_counter.most_common(10),
        "top_semantic_actions": semantic_counter.most_common(10),
        "top_targets": target_counter.most_common(10),
        "top_semantic_targets": semantic_target_counter.most_common(10),
        "max_same_action_streak": _repeat_streak(actions),
        "max_same_semantic_action_streak": _repeat_streak(semantics),
        "max_same_target_streak": _repeat_streak(targets),
        "max_same_semantic_target_streak": _repeat_streak(semantic_target),
    }


def recent_semantic_target_streak(
    transcript: List[Dict[str, Any]],
    *,
    window: int = 8,
) -> Dict[str, Any]:
    """Return the current trailing semantic_action:target streak.

    This is intentionally small and deterministic so the player-agent prompt can
    apply pressure before the run reaches long-run warning thresholds.
    """
    rows = [row for row in transcript if isinstance(row, dict)]
    if int(window or 0) > 0:
        rows = rows[-int(window or 0):]
    pairs: List[str] = []
    extracted_pairs: List[Dict[str, Any]] = []
    for row in rows:
        pair = canonical_semantic_pair_from_turn(row)
        extracted_pairs.append(pair)
        pairs.append(_safe_str(pair.get("pair")) or "unknown:unknown")

    if not pairs:
        return {
            "ok": True,
            "pair": "",
            "semantic_action": "",
            "target": "",
            "streak": 0,
            "pairs": [],
            "extracted_pairs": [],
            "source": "canonical_semantic_pair_from_turn",
        }

    current = pairs[-1]
    streak = 0
    for pair in reversed(pairs):
        if pair != current:
            break
        streak += 1

    semantic, _, target = current.partition(":")
    return {
        "ok": True,
        "pair": current,
        "semantic_action": semantic,
        "target": target,
        "streak": streak,
        "pairs": pairs,
        "extracted_pairs": extracted_pairs,
        "source": "canonical_semantic_pair_from_turn",
    }


def summarize_progress_timeline(transcript: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in (transcript if isinstance(transcript, list) else [])]
    timeline: List[Dict[str, Any]] = []
    previous_location = ""
    previous_quest_count = 0
    previous_journal_count = 0
    previous_npc_signal_count = 0

    no_progress_flags: List[bool] = []
    storyless_flags: List[bool] = []
    noop_flags: List[bool] = []
    location_changes = 0
    quest_progress_turns = 0
    journal_entry_turns = 0
    npc_signal_turns = 0
    story_beat_turns = 0

    for index, row in enumerate(rows, start=1):
        turn = _turn_index(row, index)
        location = _location(row)
        quest_count = _quest_count(row)
        journal_count = _journal_entry_count(row)
        npc_signal_count = _npc_signal_count(row)
        story_beat = _has_story_beat(row)
        reason = _result_reason(row)
        noop = _is_noop_reason(reason)

        location_changed = bool(previous_location and location and location != previous_location)
        quest_changed = quest_count > previous_quest_count
        journal_changed = journal_count > previous_journal_count
        npc_signal_changed = npc_signal_count > previous_npc_signal_count

        if location_changed:
            location_changes += 1
        if quest_changed:
            quest_progress_turns += 1
        if journal_changed:
            journal_entry_turns += 1
        if npc_signal_changed:
            npc_signal_turns += 1
        if story_beat:
            story_beat_turns += 1

        meaningful_progress = any(
            [
                location_changed,
                quest_changed,
                journal_changed,
                npc_signal_changed,
                story_beat,
            ]
        ) and not noop

        no_progress_flags.append(not meaningful_progress)
        storyless_flags.append(not story_beat)
        noop_flags.append(noop)

        timeline.append(
            {
                "turn_index": turn,
                "semantic_action": _semantic_action(row),
                "target": _target(row),
                "location": location,
                "location_changed": location_changed,
                "quest_count": quest_count,
                "quest_changed": quest_changed,
                "journal_entry_count": journal_count,
                "journal_changed": journal_changed,
                "npc_signal_count": npc_signal_count,
                "npc_signal_changed": npc_signal_changed,
                "story_beat": story_beat,
                "noop": noop,
                "reason": reason,
                "meaningful_progress": meaningful_progress,
                "manual_error": _manual_error(row),
            }
        )

        if location:
            previous_location = location
        previous_quest_count = max(previous_quest_count, quest_count)
        previous_journal_count = max(previous_journal_count, journal_count)
        previous_npc_signal_count = max(previous_npc_signal_count, npc_signal_count)

    turns = len(rows)
    meaningful_turns = sum(1 for item in timeline if item.get("meaningful_progress"))
    return {
        "turns": turns,
        "meaningful_progress_turns": meaningful_turns,
        "meaningful_progress_rate": round(meaningful_turns / turns, 4) if turns else 0.0,
        "story_beat_turns": story_beat_turns,
        "story_beat_rate": round(story_beat_turns / turns, 4) if turns else 0.0,
        "location_changes": location_changes,
        "quest_progress_turns": quest_progress_turns,
        "journal_entry_turns": journal_entry_turns,
        "npc_signal_turns": npc_signal_turns,
        "noop_turns": sum(1 for item in noop_flags if item),
        "noop_rate": round(sum(1 for item in noop_flags if item) / turns, 4) if turns else 0.0,
        "max_no_progress_streak": _max_streak(no_progress_flags),
        "max_storyless_streak": _max_streak(storyless_flags),
        "max_noop_streak": _max_streak(noop_flags),
        "timeline": timeline[-150:],
    }


def summarize_long_run_warnings(
    *,
    transcript: List[Dict[str, Any]],
    action_diversity_summary: Dict[str, Any],
    progress_timeline_summary: Dict[str, Any],
    console_log_summary: Dict[str, Any],
    manual_turn_error_summary: Dict[str, Any],
    turns_for_strict_gates: int = 100,
    campaign_complete_waiting: bool = False,
) -> Dict[str, Any]:
    rows = [_safe_dict(row) for row in (transcript if isinstance(transcript, list) else [])]
    turn_count = len(rows)
    strict = turn_count >= turns_for_strict_gates
    warnings: List[Dict[str, Any]] = []

    def add(code: str, severity: str, message: str, details: Dict[str, Any] | None = None) -> None:
        warnings.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "details": details or {},
            }
        )

    same_semantic_target_streak = int(
        _safe_dict(action_diversity_summary.get("max_same_semantic_target_streak")).get("streak") or 0
    )
    if same_semantic_target_streak >= (8 if strict else 5) and not campaign_complete_waiting:
        add(
            "repeated_semantic_target_streak",
            "error" if strict else "warning",
            "The player-agent repeated the same semantic action/target too many times.",
            _safe_dict(action_diversity_summary.get("max_same_semantic_target_streak")),
        )

    unknown_semantic_rate = float(action_diversity_summary.get("unknown_semantic_rate") or 0.0)
    if unknown_semantic_rate >= (0.25 if strict else 0.75):
        add(
            "semantic_action_extraction_unknown_rate",
            "error" if strict else "warning",
            "Too many turns have unknown semantic action classification.",
            {
                "unknown_semantic_rate": unknown_semantic_rate,
                "unknown_semantic_count": action_diversity_summary.get("unknown_semantic_count"),
            },
        )

    no_progress_streak = int(progress_timeline_summary.get("max_no_progress_streak") or 0)
    if no_progress_streak >= (10 if strict else 6):
        add(
            "no_progress_streak",
            "error" if strict else "warning",
            "The run had a long streak without meaningful progress.",
            {"max_no_progress_streak": no_progress_streak},
        )

    storyless_streak = int(progress_timeline_summary.get("max_storyless_streak") or 0)
    if storyless_streak >= (12 if strict else 8):
        add(
            "storyless_streak",
            "error" if strict else "warning",
            "The run had a long streak without story beats.",
            {"max_storyless_streak": storyless_streak},
        )

    noop_streak = int(progress_timeline_summary.get("max_noop_streak") or 0)
    if noop_streak >= (5 if strict else 3):
        add(
            "noop_streak",
            "error" if strict else "warning",
            "The run had repeated no-op/internal failure results.",
            {"max_noop_streak": noop_streak},
        )

    if int(_safe_dict(console_log_summary).get("turn_error_count") or 0) > 0:
        add(
            "console_turn_errors",
            "error",
            "Console log contains TURN N ERROR lines.",
            {"turn_errors": _safe_list(console_log_summary.get("turn_errors"))[:10]},
        )

    if int(_safe_dict(manual_turn_error_summary).get("error_count") or 0) > 0:
        add(
            "manual_turn_errors",
            "error",
            "Transcript rows contain manual turn runtime errors.",
            {"errors": _safe_list(manual_turn_error_summary.get("errors"))[:10]},
        )

    error_count = sum(1 for warning in warnings if warning.get("severity") == "error")
    warning_count = sum(1 for warning in warnings if warning.get("severity") == "warning")
    return {
        "ok": error_count == 0,
        "turn_count": turn_count,
        "strict_100_turn_mode": strict,
        "warning_count": warning_count,
        "error_count": error_count,
        "warnings": warnings,
    }


def summarize_hundred_turn_eval(
    *,
    transcript: List[Dict[str, Any]],
    summary: Dict[str, Any],
    turns_for_strict_gates: int = 100,
) -> Dict[str, Any]:
    action = summarize_action_diversity(transcript)
    progress = summarize_progress_timeline(transcript)
    warnings = summarize_long_run_warnings(
        transcript=transcript,
        action_diversity_summary=action,
        progress_timeline_summary=progress,
        console_log_summary=_safe_dict(summary.get("console_log_summary")),
        manual_turn_error_summary=_safe_dict(summary.get("manual_turn_error_summary")),
        turns_for_strict_gates=turns_for_strict_gates,
    )
    turn_count = len(transcript if isinstance(transcript, list) else [])
    return {
        "ok": bool(warnings.get("ok")),
        "turn_count": turn_count,
        "strict_100_turn_mode": turn_count >= turns_for_strict_gates,
        "readiness": "strict" if turn_count >= turns_for_strict_gates else "smoke",
        "action_diversity_summary": action,
        "progress_timeline_summary": progress,
        "long_run_warning_summary": warnings,
    }