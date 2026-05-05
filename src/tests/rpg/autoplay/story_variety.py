from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _hash(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_story_signature_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    director = _safe_dict(state.get("campaign_director_state"))
    lore_entries = _safe_list(_safe_dict(state.get("lore_state")).get("entries"))
    npc_profiles = _safe_dict(_safe_dict(state.get("npc_profile_state")).get("profiles"))
    arcs = _safe_dict(_safe_dict(state.get("story_arc_state")).get("arcs"))
    milestones_by_arc = _safe_dict(_safe_dict(state.get("story_arc_milestone_state")).get("arcs"))

    milestone_titles = []
    for bucket in milestones_by_arc.values():
        for milestone in _safe_list(_safe_dict(bucket).get("milestones")):
            milestone = _safe_dict(milestone)
            title = _safe_str(milestone.get("title") or milestone.get("milestone_id"))
            if title:
                milestone_titles.append(title)

    signature = {
        "campaign_title": director.get("campaign_title"),
        "premise": director.get("premise"),
        "dramatic_question": director.get("dramatic_question"),
        "lore_titles": sorted(
            _safe_str(row.get("title") or row.get("id"))
            for row in lore_entries
            if _safe_str(row.get("title") or row.get("id"))
        ),
        "npc_names": sorted(
            _safe_str(profile.get("name") or key)
            for key, profile in npc_profiles.items()
            if _safe_str(_safe_dict(profile).get("name") or key)
        ),
        "arc_titles": sorted(
            _safe_str(arc.get("title") or arc_id)
            for arc_id, arc in arcs.items()
            if _safe_str(_safe_dict(arc).get("title") or arc_id)
        ),
        "milestone_titles": sorted(milestone_titles),
    }
    signature["signature_hash"] = _hash(signature)
    return signature


def compute_story_variety_metrics(
    *,
    summary: Dict[str, Any],
    state: Dict[str, Any],
    transcript: List[Dict[str, Any]],
) -> Dict[str, Any]:
    signature = extract_story_signature_from_state(state)
    hook_ids = []
    dialogue_sources = []
    for row in transcript:
        for hook in _safe_list(row.get("story_hook_result", {}).get("fired_hooks")):
            hook = _safe_dict(hook)
            if hook.get("hook_id"):
                hook_ids.append(str(hook.get("hook_id")))
        if row.get("dialogue_source"):
            dialogue_sources.append(str(row.get("dialogue_source")))
    branch_path = {
        "hook_ids": hook_ids,
        "dialogue_sources": dialogue_sources,
    }
    return {
        "requested_seed": summary.get("scenario_seed"),
        "resolved_seed": summary.get("resolved_scenario_seed") or summary.get("scenario_seed"),
        "random_seed": _safe_dict(summary.get("seed_resolution")).get("random_seed"),
        "randomized": _safe_dict(summary.get("seed_resolution")).get("randomized", False),
        "story_signature": signature,
        "branch_path": branch_path,
        "branch_signature_hash": _hash(branch_path),
        "story_variety_key": _hash(
            {
                "seed": summary.get("resolved_scenario_seed") or summary.get("scenario_seed"),
                "story_signature_hash": signature.get("signature_hash"),
                "branch_signature_hash": _hash(branch_path),
            }
        ),
    }