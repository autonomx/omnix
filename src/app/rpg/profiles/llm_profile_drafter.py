from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_profile_draft_prompt(profile: Dict[str, Any]) -> str:
    profile = _safe_dict(profile)
    return (
        "You are drafting editable NPC character-card text for a deterministic RPG engine.\n"
        "Do not invent world-changing secrets, quest outcomes, hidden knowledge, or facts that imply new simulation truth.\n"
        "You may add flavor, personality texture, speech style, and plausible background consistent with the structured scaffold.\n"
        "Return STRICT JSON only with keys: biography, history, personality.\n\n"
        "Scaffold:\n"
        f"{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        "Required JSON shape:\n"
        "{\n"
        '  "biography": {\n'
        '    "short_summary": "...",\n'
        '    "full_biography": "...",\n'
        '    "public_reputation": "...",\n'
        '    "private_notes": "..."\n'
        "  },\n"
        '  "history": {\n'
        '    "background": "...",\n'
        '    "major_life_events": [],\n'
        '    "recent_events": []\n'
        "  },\n"
        '  "personality": {\n'
        '    "traits": [],\n'
        '    "temperament": "...",\n'
        '    "speech_style": "...",\n'
        '    "risk_tolerance": "...",\n'
        '    "conflict_style": "..."\n'
        "  }\n"
        "}\n"
    )


def validate_profile_draft(draft: Dict[str, Any]) -> Dict[str, Any]:
    draft = _safe_dict(draft)

    biography = _safe_dict(draft.get("biography"))
    history = _safe_dict(draft.get("history"))
    personality = _safe_dict(draft.get("personality"))

    clean = {
        "biography": {
            "short_summary": _safe_str(biography.get("short_summary"))[:500],
            "full_biography": _safe_str(biography.get("full_biography"))[:4000],
            "public_reputation": _safe_str(biography.get("public_reputation"))[:1000],
            "private_notes": _safe_str(biography.get("private_notes"))[:1500],
        },
        "history": {
            "background": _safe_str(history.get("background"))[:3000],
            "major_life_events": history.get("major_life_events") if isinstance(history.get("major_life_events"), list) else [],
            "recent_events": history.get("recent_events") if isinstance(history.get("recent_events"), list) else [],
        },
        "personality": {
            "traits": personality.get("traits") if isinstance(personality.get("traits"), list) else [],
            "temperament": _safe_str(personality.get("temperament"))[:500],
            "speech_style": _safe_str(personality.get("speech_style"))[:500],
            "risk_tolerance": _safe_str(personality.get("risk_tolerance"))[:100],
            "conflict_style": _safe_str(personality.get("conflict_style"))[:500],
        },
    }

    clean["history"]["major_life_events"] = clean["history"]["major_life_events"][:12]
    clean["history"]["recent_events"] = clean["history"]["recent_events"][:12]
    clean["personality"]["traits"] = [
        _safe_str(item)[:64]
        for item in clean["personality"]["traits"][:12]
        if _safe_str(item)
    ]

    return clean


def merge_profile_draft(profile: Dict[str, Any], draft: Dict[str, Any]) -> Dict[str, Any]:
    profile = deepcopy(_safe_dict(profile))
    draft = validate_profile_draft(draft)

    for section in ("biography", "history", "personality"):
        merged = _safe_dict(profile.get(section))
        for key, value in _safe_dict(draft.get(section)).items():
            if value not in ("", [], {}):
                merged[key] = value
        profile[section] = merged

    profile["origin"] = "llm_drafted_from_scaffold"
    return profile


async def maybe_draft_profile_with_llm(
    profile: Dict[str, Any],
    *,
    provider: Any = None,
) -> Dict[str, Any]:
    """Optional drafter.

    This is intentionally provider-injected. If no provider is passed, return a
    skipped result so normal gameplay never depends on the LLM drafter.
    """
    profile = _safe_dict(profile)
    if provider is None:
        return {
            "drafted": False,
            "reason": "llm_provider_not_available",
            "profile": deepcopy(profile),
            "source": "deterministic_profile_drafter",
        }

    prompt = build_profile_draft_prompt(profile)

    try:
        raw = await provider.complete(prompt)
        data = json.loads(_safe_str(raw))
        merged = merge_profile_draft(profile, data)
        return {
            "drafted": True,
            "profile": merged,
            "raw": _safe_str(raw)[:8000],
            "source": "deterministic_profile_drafter",
        }
    except Exception as exc:
        return {
            "drafted": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "profile": deepcopy(profile),
            "source": "deterministic_profile_drafter",
        }
