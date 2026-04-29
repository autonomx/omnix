from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List

SUPPORTED_ACTION_KINDS = {
    "inspect",
    "open",
    "close",
    "take",
    "drop",
    "give",
    "put",
    "use",
    "repair",
    "equip",
    "unequip",
    "attack",
    "talk",
    "unknown",
}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _safe_str(value).strip().lower())


def _clean_target_ref(value: str) -> str:
    value = _safe_str(value).strip()
    value = re.sub(r"^(the|a|an|my|his|her|their|this|that)\s+", "", value, flags=re.I)
    value = value.strip(" .,!?:;\"'")
    return value


def _parse_leading_quantity(target_ref: str) -> tuple[int, str]:
    value = _safe_str(target_ref).strip()

    match = re.match(r"^(\d+)\s+(.+)$", value)
    if match:
        return max(1, int(match.group(1))), _clean_target_ref(match.group(2))

    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    parts = value.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in word_numbers:
        return word_numbers[parts[0].lower()], _clean_target_ref(parts[1])

    return 1, _clean_target_ref(value)


def _extract_after_markers(text: str, markers: List[str]) -> str:
    for marker in markers:
        if marker in text:
            return _clean_target_ref(text.split(marker, 1)[1])
    return ""


def _first_match(patterns: List[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return _clean_target_ref(match.group(1))
    return ""


def resolve_semantic_action_v2(
    *,
    player_input: str,
    actor_id: str = "player",
) -> Dict[str, Any]:
    """Resolve free text to a bounded semantic action.

    This is deliberately conservative. It recognizes common interaction shapes
    but does not mutate world/inventory/combat state.
    """
    raw = _safe_str(player_input)
    text = _normalize_text(raw)

    if not text:
        return {
            "resolved": False,
            "kind": "unknown",
            "actor_id": actor_id,
            "reason": "empty_player_input",
            "source": "deterministic_semantic_action_resolver_v2",
        }

    # talk/direct speech is already handled elsewhere, but expose a semantic tag.
    if re.search(r"\b(talk to|speak to|ask|tell)\b", text):
        target = _first_match(
            [
                r"\b(?:talk to|speak to|ask|tell)\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "talk",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "medium",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(inspect|examine|look at|study|check)\b", text):
        target = _first_match(
            [
                r"\b(?:inspect|examine|look at|study|check)\s+([^,.!?]+)",
                r"\blook\s+over\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "inspect",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(open|unlock)\b", text):
        target = _first_match(
            [
                r"\b(?:open|unlock)\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "open",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(close|shut|lock)\b", text):
        target = _first_match(
            [
                r"\b(?:close|shut|lock)\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "close",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(take|pick up|grab|collect)\b", text):
        target = _first_match(
            [
                r"\b(?:take|grab|collect)\s+([^,.!?]+)",
                r"\bpick up\s+([^,.!?]+)",
            ],
            text,
        )
        quantity, clean_target = _parse_leading_quantity(target)
        return {
            "resolved": True,
            "kind": "take",
            "actor_id": actor_id,
            "target_ref": clean_target,
            "quantity": quantity,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(drop|discard|put down)\b", text):
        target = _first_match(
            [
                r"\b(?:drop|discard)\s+([^,.!?]+)",
                r"\bput down\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "drop",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(give|hand|offer)\b", text):
        item_ref = ""
        recipient_ref = ""

        # "give Bran the dagger"
        match = re.search(r"\b(?:give|hand|offer)\s+([^,.!?]+?)\s+(?:the|a|an|my)?\s*([^,.!?]+)$", text, re.I)
        if match:
            recipient_ref = _clean_target_ref(match.group(1))
            item_ref = _clean_target_ref(match.group(2))

        # "give the dagger to Bran"
        match = re.search(r"\b(?:give|hand|offer)\s+([^,.!?]+?)\s+to\s+([^,.!?]+)", text, re.I)
        if match:
            item_ref = _clean_target_ref(match.group(1))
            recipient_ref = _clean_target_ref(match.group(2))

        return {
            "resolved": True,
            "kind": "give",
            "actor_id": actor_id,
            "target_ref": item_ref,
            "secondary_target_ref": recipient_ref,
            "item_ref": item_ref,
            "recipient_ref": recipient_ref,
            "confidence": "high" if item_ref and recipient_ref else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(put|place|stow)\b", text):
        item_ref = ""
        container_ref = ""
        quantity = 1

        match = re.search(r"\b(?:put|place|stow)\s+([^,.!?]+?)\s+(?:into|in|inside)\s+([^,.!?]+)", text, re.I)
        if match:
            raw_item = _clean_target_ref(match.group(1))
            quantity, item_ref = _parse_leading_quantity(raw_item)
            container_ref = _clean_target_ref(match.group(2))

        return {
            "resolved": True,
            "kind": "put",
            "actor_id": actor_id,
            "target_ref": item_ref,
            "secondary_target_ref": container_ref,
            "quantity": quantity,
            "confidence": "high" if item_ref and container_ref else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(use)\b", text):
        item_ref = ""
        target_ref = ""

        # "use rope on well"
        match = re.search(r"\buse\s+([^,.!?]+?)\s+(?:on|with)\s+([^,.!?]+)", text, re.I)
        if match:
            item_ref = _clean_target_ref(match.group(1))
            target_ref = _clean_target_ref(match.group(2))
        else:
            item_ref = _extract_after_markers(text, ["use "])

        return {
            "resolved": True,
            "kind": "use",
            "actor_id": actor_id,
            "target_ref": target_ref or item_ref,
            "secondary_target_ref": target_ref,
            "item_ref": item_ref,
            "confidence": "high" if item_ref else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(repair|fix|mend)\b", text):
        target_ref = ""
        tool_ref = ""
        secondary_quantity = 1

        match = re.search(r"\b(?:repair|fix|mend)\s+(.+)$", text, re.I)
        if match:
            remainder = _clean_target_ref(match.group(1))
            if " with " in remainder:
                target_part, tool_part = remainder.split(" with ", 1)
                target_ref = _clean_target_ref(target_part)
                secondary_quantity, tool_ref = _parse_leading_quantity(tool_part)
            else:
                target_ref = _clean_target_ref(remainder)

        return {
            "resolved": True,
            "kind": "repair",
            "actor_id": actor_id,
            "target_ref": target_ref,
            "secondary_target_ref": tool_ref,
            "tool_ref": tool_ref,
            "secondary_quantity": secondary_quantity,
            "confidence": "high" if target_ref else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(equip|wear|wield)\b", text):
        target = _first_match(
            [
                r"\b(?:equip|wear|wield)\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "equip",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(unequip|remove)\b", text):
        target = _first_match(
            [
                r"\b(?:unequip|remove)\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "unequip",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    if re.search(r"\b(attack|strike|hit|stab|shoot)\b", text):
        target = _first_match(
            [
                r"\b(?:attack|strike|hit|stab|shoot)\s+([^,.!?]+)",
            ],
            text,
        )
        return {
            "resolved": True,
            "kind": "attack",
            "actor_id": actor_id,
            "target_ref": target,
            "confidence": "high" if target else "low",
            "raw_input": raw,
            "source": "deterministic_semantic_action_resolver_v2",
        }

    return {
        "resolved": False,
        "kind": "unknown",
        "actor_id": actor_id,
        "target_ref": "",
        "confidence": "none",
        "raw_input": raw,
        "reason": "no_supported_semantic_action_detected",
        "source": "deterministic_semantic_action_resolver_v2",
    }


def semantic_action_kind(action: Dict[str, Any]) -> str:
    kind = _safe_str(_safe_dict(action).get("kind"))
    return kind if kind in SUPPORTED_ACTION_KINDS else "unknown"
