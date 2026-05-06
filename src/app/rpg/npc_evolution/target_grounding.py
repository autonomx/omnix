from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List, Tuple


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


ROLE_ALIASES = {
    "innkeeper": {"innkeeper", "barkeep", "bartender", "tavern keeper", "host", "keeper"},
    "guard": {"guard", "watchman", "watch", "sentinel"},
    "merchant": {"merchant", "shopkeeper", "vendor", "trader"},
    "blacksmith": {"blacksmith", "smith"},
    "healer": {"healer", "priest", "medic"},
}


NON_NPC_TARGETS = {
    "player",
    "the player",
    "you",
    "self",
    "environment",
    "room",
    "scene",
    "unknown",
    "none",
    "n/a",
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _safe_str(value).strip().lower())


def _id_variants(value: Any) -> set[str]:
    raw = _safe_str(value).strip()
    normed = _norm(raw)
    variants = {normed} if normed else set()
    if normed.startswith("npc:"):
        variants.add(normed.split("npc:", 1)[1])
    elif normed:
        variants.add(f"npc:{normed}")
    return {item for item in variants if item}


def _known_npcs(simulation_state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    simulation_state = _safe_dict(simulation_state)
    candidates = [
        _safe_dict(simulation_state.get("npcs")),
        _safe_dict(_safe_dict(simulation_state.get("npc_progression_state")).get("npcs")),
        _safe_dict(_safe_dict(simulation_state.get("npc_profile_state")).get("npcs")),
    ]
    for candidate in candidates:
        if candidate:
            return {str(k): _safe_dict(v) for k, v in candidate.items()}
    return {}


def _present_npc_items(simulation_state: Dict[str, Any]) -> List[Any]:
    simulation_state = _safe_dict(simulation_state)
    direct = (
        _safe_list(simulation_state.get("present_npcs"))
        or _safe_list(simulation_state.get("nearby_npcs"))
        or _safe_list(simulation_state.get("visible_npcs"))
    )
    if direct:
        return direct

    scene = _safe_dict(simulation_state.get("scene"))
    scene_items = (
        _safe_list(scene.get("present_npcs"))
        or _safe_list(scene.get("nearby_npcs"))
        or _safe_list(scene.get("visible_npcs"))
    )
    if scene_items:
        return scene_items

    contract = _safe_dict(simulation_state.get("turn_contract"))
    for section_key in ("resolved_action", "resolved_result"):
        section = _safe_dict(contract.get(section_key))
        location = _safe_dict(_safe_dict(section.get("location_state")).get("current_location"))
        present = _safe_list(location.get("present_npcs"))
        if present:
            return present

    return []


def _item_id(item: Any) -> str:
    if isinstance(item, str):
        return item
    item_dict = _safe_dict(item)
    return (
        _safe_str(item_dict.get("id"))
        or _safe_str(item_dict.get("npc_id"))
        or _safe_str(item_dict.get("name"))
    )


def _present_npc_ids(simulation_state: Dict[str, Any]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in _present_npc_items(simulation_state):
        npc_id = _item_id(item)
        if not npc_id:
            continue
        canonical = _canonical_npc_id(simulation_state, npc_id)
        if canonical:
            npc_id = canonical
        marker = npc_id.lower()
        if marker in seen:
            continue
        seen.add(marker)
        out.append(npc_id)
    return out


def _npc_record_names(npc_id: str, record: Dict[str, Any]) -> List[str]:
    names = [
        npc_id,
        _safe_str(record.get("name")),
        _safe_str(record.get("display_name")),
        _safe_str(record.get("title")),
    ]
    aliases = record.get("aliases")
    if isinstance(aliases, list):
        names.extend(_safe_str(alias) for alias in aliases)
    return [name for name in names if _safe_str(name)]


def _npc_role_terms(record: Dict[str, Any]) -> List[str]:
    role = _norm(record.get("role") or record.get("occupation") or record.get("job"))
    terms = set()
    if role:
        terms.add(role)
        terms.update(ROLE_ALIASES.get(role, set()))
    for key in ("tags", "traits"):
        values = record.get(key)
        if isinstance(values, list):
            for value in values:
                normed = _norm(value)
                if normed:
                    terms.add(normed)
                    terms.update(ROLE_ALIASES.get(normed, set()))
    return sorted(terms)


def _projection_text(projection: Dict[str, Any]) -> str:
    projection = _safe_dict(projection)
    payload = _safe_dict(projection.get("payload"))
    parts = [
        projection.get("kind"),
        payload.get("target"),
        payload.get("owner"),
        payload.get("npc"),
        payload.get("npc_id"),
        payload.get("summary"),
        payload.get("description"),
        payload.get("reason"),
        payload.get("intent"),
        payload.get("type"),
    ]
    return " ".join(_safe_str(part) for part in parts if _safe_str(part)).lower()


def _explicit_target(projection: Dict[str, Any]) -> str:
    payload = _safe_dict(_safe_dict(projection).get("payload"))
    return (
        _safe_str(payload.get("target"))
        or _safe_str(payload.get("owner"))
        or _safe_str(payload.get("npc"))
        or _safe_str(payload.get("npc_id"))
    )


def _npc_exists(simulation_state: Dict[str, Any], npc_id: str) -> bool:
    if not npc_id:
        return False
    marker = npc_id.lower()
    npcs = _known_npcs(simulation_state)
    if npc_id in npcs:
        return True
    if marker in {str(key).lower() for key in npcs.keys()}:
        return True
    return marker in {str(item).lower() for item in _present_npc_ids(simulation_state)}


def _canonical_npc_id(simulation_state: Dict[str, Any], candidate: str) -> str:
    candidate_variants = _id_variants(candidate)
    if not candidate_variants:
        return ""
    npcs = _known_npcs(simulation_state)
    for npc_id, record in npcs.items():
        names = set()
        for name in _npc_record_names(npc_id, record):
            names.update(_id_variants(name))
        if candidate_variants & names:
            return str(npc_id)
    for npc_id in _present_npc_ids(simulation_state):
        if candidate_variants & _id_variants(npc_id):
            return npc_id
    return ""


def ground_projection_target(
    *,
    projection: Dict[str, Any],
    simulation_state: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Deterministically ground ambiguous projection target to a known NPC.

    Grounding order:
      1. explicit known target/name/alias
      2. explicit role alias matched against present NPC roles
      3. NPC name mentioned in summary/text
      4. role alias mentioned in summary/text and exactly one matching present NPC
      5. exactly one present NPC

    Returns (projection_copy, grounding_result).
    """
    projection = deepcopy(_safe_dict(projection))
    payload = projection.setdefault("payload", {})
    simulation_state = _safe_dict(simulation_state)
    npcs = _known_npcs(simulation_state)
    present_ids = _present_npc_ids(simulation_state)
    text = _projection_text(projection)

    explicit = _explicit_target(projection)
    explicit_norm = _norm(explicit)
    if explicit_norm and explicit_norm not in NON_NPC_TARGETS:
        canonical = _canonical_npc_id(simulation_state, explicit)
        if canonical:
            payload["target"] = canonical
            payload.setdefault("grounded_target", canonical)
            projection["target_grounding"] = {
                "grounded": True,
                "npc_id": canonical,
                "reason": "explicit_known_target",
                "original_target": explicit,
            }
            return projection, projection["target_grounding"]

        # Role alias from explicit target, for example "innkeeper" -> Bran.
        role_matches = []
        for npc_id in present_ids or list(npcs.keys()):
            record = _safe_dict(npcs.get(npc_id))
            role_terms = set(_npc_role_terms(record))
            if explicit_norm in role_terms:
                role_matches.append(str(npc_id))
        if len(role_matches) == 1:
            npc_id = role_matches[0]
            payload["target"] = npc_id
            payload.setdefault("grounded_target", npc_id)
            projection["target_grounding"] = {
                "grounded": True,
                "npc_id": npc_id,
                "reason": "explicit_role_alias",
                "original_target": explicit,
            }
            return projection, projection["target_grounding"]

    # Name/alias mentioned in text.
    for npc_id, record in npcs.items():
        for name in _npc_record_names(npc_id, record):
            norm_name = _norm(name)
            if norm_name and norm_name in text:
                payload["target"] = str(npc_id)
                payload.setdefault("grounded_target", str(npc_id))
                projection["target_grounding"] = {
                    "grounded": True,
                    "npc_id": str(npc_id),
                    "reason": "name_mentioned_in_projection_text",
                    "matched": name,
                }
                return projection, projection["target_grounding"]

    # Role alias mentioned in text and exactly one matching present NPC.
    role_matches = []
    for npc_id in present_ids or list(npcs.keys()):
        record = _safe_dict(npcs.get(npc_id))
        role_terms = set(_npc_role_terms(record))
        if any(term and term in text for term in role_terms):
            role_matches.append(str(npc_id))
    role_matches = sorted(set(role_matches))
    if len(role_matches) == 1:
        npc_id = role_matches[0]
        payload["target"] = npc_id
        payload.setdefault("grounded_target", npc_id)
        projection["target_grounding"] = {
            "grounded": True,
            "npc_id": npc_id,
            "reason": "role_alias_mentioned_in_projection_text",
        }
        return projection, projection["target_grounding"]

    if len(present_ids) == 1:
        npc_id = present_ids[0]
        payload["target"] = npc_id
        payload.setdefault("grounded_target", npc_id)
        projection["target_grounding"] = {
            "grounded": True,
            "npc_id": npc_id,
            "reason": "single_present_npc",
        }
        return projection, projection["target_grounding"]

    projection["target_grounding"] = {
        "grounded": False,
        "npc_id": "",
        "reason": "no_deterministic_target",
        "present_npc_count": len(present_ids),
        "known_npc_count": len(npcs),
    }
    return projection, projection["target_grounding"]