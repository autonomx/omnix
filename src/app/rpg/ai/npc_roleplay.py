from __future__ import annotations

import json
import re
from typing import Any, Dict, List

FORBIDDEN_EFFECT_KEYS = {
    "quest_started",
    "quest_completed",
    "reward",
    "reward_granted",
    "item_created",
    "currency_delta",
    "currency_changed",
    "stock_update",
    "stock_changed",
    "journal_entry",
    "journal_entry_created",
    "transaction_record",
    "inventory_delta",
    "location_changed",
    "combat_started",
    "npc_moved",
}


FORBIDDEN_CLAIM_PATTERNS = [
    re.compile(r"\b(reward|payment|gold|silver|coins?)\b", re.IGNORECASE),
    re.compile(r"\b(take this|give you|grant you|you receive)\b", re.IGNORECASE),
    re.compile(r"\b(quest completed|quest started|new quest)\b", re.IGNORECASE),
    re.compile(r"\b(i know where|hidden treasure|secret lair)\b", re.IGNORECASE),
]


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _safe_str(text).strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}


def build_npc_roleplay_prompt(profile: Dict[str, Any]) -> str:
    profile = _safe_dict(profile)
    return (
        "You are writing ONE line of NPC dialogue for a deterministic RPG engine.\n"
        "You may shape tone from the NPC biography, but you may not create world facts.\n"
        "Only use allowed_facts. If the player asks about an unbacked topic, safely deflect.\n"
        "Return strict JSON only with this schema:\n"
        "{\n"
        '  "speaker_id": string,\n'
        '  "speaker_name": string,\n'
        '  "line": string,\n'
        '  "style_tags": [string],\n'
        '  "used_fact_ids": [string],\n'
        '  "claims": [string],\n'
        '  "forbidden_effects": []\n'
        "}\n\n"
        f"NPC profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n"
    )


def validate_npc_roleplay_output(
    output: Dict[str, Any],
    *,
    expected_speaker_id: str,
    profile: Dict[str, Any],
    max_line_chars: int = 240,
) -> Dict[str, Any]:
    output = _safe_dict(output)
    profile = _safe_dict(profile)
    violations: List[str] = []

    speaker_id = _safe_str(output.get("speaker_id"))
    line = _safe_str(output.get("line")).strip()
    used_fact_ids = [_safe_str(value) for value in _safe_list(output.get("used_fact_ids"))]
    allowed_fact_ids = set(_safe_str(value) for value in _safe_list(profile.get("used_fact_ids")))
    forbidden_effects = _safe_list(output.get("forbidden_effects"))

    if speaker_id != expected_speaker_id:
        violations.append("speaker_id_mismatch")
    if not line:
        violations.append("empty_line")
    if len(line) > max_line_chars:
        violations.append("line_too_long")

    for key in FORBIDDEN_EFFECT_KEYS:
        if output.get(key):
            violations.append(f"forbidden_effect_key:{key}")

    for effect in forbidden_effects:
        text = _safe_str(effect)
        if text:
            violations.append(f"forbidden_effect_declared:{text}")

    for fact_id in used_fact_ids:
        if fact_id and fact_id not in allowed_fact_ids:
            violations.append(f"unbacked_fact_id:{fact_id}")

    for pattern in FORBIDDEN_CLAIM_PATTERNS:
        if pattern.search(line):
            # Permit the word "reward" only if an allowed fact explicitly contains it.
            allowed_text = " ".join(_safe_str(value).lower() for value in _safe_list(profile.get("allowed_facts")))
            if pattern.pattern.lower() not in allowed_text:
                violations.append("forbidden_claim_pattern")
                break

    return {
        "ok": not violations,
        "violations": violations,
        "line": line,
        "source": "npc_roleplay_validator",
    }


async def try_generate_npc_roleplay_line(
    *,
    profile: Dict[str, Any],
    expected_speaker_id: str,
    provider: Any = None,
    enabled: bool = False,
) -> Dict[str, Any]:
    if not enabled:
        return {
            "ok": False,
            "roleplay_source": "llm_disabled",
            "error": "npc_roleplay_llm_disabled",
        }

    if provider is None:
        return {
            "ok": False,
            "roleplay_source": "llm_unavailable",
            "error": "provider_unavailable",
        }

    prompt = build_npc_roleplay_prompt(profile)
    try:
        if hasattr(provider, "generate"):
            raw = await provider.generate(prompt) if callable(provider.generate) else ""
        elif hasattr(provider, "complete"):
            raw = await provider.complete(prompt) if callable(provider.complete) else ""
        else:
            return {
                "ok": False,
                "roleplay_source": "llm_unavailable",
                "error": "provider_has_no_generate_method",
            }
    except Exception as exc:
        return {
            "ok": False,
            "roleplay_source": "llm_error",
            "error": f"{type(exc).__name__}: {exc}",
        }

    parsed = _extract_json_object(_safe_str(raw))
    validation = validate_npc_roleplay_output(
        parsed,
        expected_speaker_id=expected_speaker_id,
        profile=profile,
    )
    if not validation.get("ok"):
        return {
            "ok": False,
            "roleplay_source": "llm_fallback",
            "raw": _safe_str(raw)[:2000],
            "parsed": parsed,
            "validation": validation,
            "error": "llm_output_failed_validation",
        }

    return {
        "ok": True,
        "roleplay_source": "llm_validated",
        "line": _safe_str(parsed.get("line")),
        "style_tags": _safe_list(parsed.get("style_tags"))[:8],
        "used_fact_ids": _safe_list(parsed.get("used_fact_ids"))[:8],
        "claims": _safe_list(parsed.get("claims"))[:8],
        "validation": validation,
        "source": "npc_roleplay_llm_boundary",
    }
