from __future__ import annotations

from typing import Any

_ALLOWED_PREFIXES = (
    "ask",
    "talk",
    "say",
    "tell",
    "look",
    "inspect",
    "check",
    "travel",
    "go",
    "walk",
    "buy",
    "sell",
    "rest",
    "attack",
    "defend",
    "cast",
    "equip",
    "use",
    "focus",
    "journal",
)
_MUTATION_KEYS = {"state_patch", "state_changes", "mutation", "before", "after", "delta"}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def hermes_planner_contract_schema() -> dict[str, Any]:
    return {
        "request": {
            "session_id": "string",
            "turn_id": "string|number|null",
            "context_hash": "string|null",
            "context": "bounded visible RPG context",
            "available_commands": "list[string]",
        },
        "response": {
            "command": "single RPG command string",
            "reason": "string",
            "confidence": "number 0..1",
            "risk": "low|medium|high",
            "expected_effect": "string",
            "direct_state_write": False,
        },
    }


def normalize_hermes_planner_response(payload: Any) -> dict[str, Any]:
    data = _safe_dict(payload)
    if not data:
        return _rejected("invalid_response")
    proposal = _safe_dict(data.get("proposal")) or data
    mutation_keys = sorted(key for key in _MUTATION_KEYS if key in data or key in proposal)
    if mutation_keys:
        return _rejected("state_mutation_not_allowed", mutation_keys=mutation_keys)

    command = _safe_str(proposal.get("command") or proposal.get("command_text")).strip()
    if not command:
        return _rejected("empty_command")
    if not _known_command(command):
        return _rejected("unknown_command", command=command)

    return {
        "ok": True,
        "accepted": True,
        "source": "hermes_planner_contract",
        "proposal": {
            "command": command,
            "reason": _safe_str(proposal.get("reason")).strip(),
            "confidence": _confidence(proposal.get("confidence")),
            "risk": _risk(_safe_str(proposal.get("risk") or "medium")),
            "expected_effect": _safe_str(proposal.get("expected_effect")).strip(),
            "requires_review": True,
            "direct_state_write": False,
        },
    }


def _known_command(command: str) -> bool:
    head = command.lower().split(maxsplit=1)[0]
    return head in _ALLOWED_PREFIXES


def _confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 1.0))


def _risk(value: str) -> str:
    lowered = value.strip().lower()
    return lowered if lowered in {"low", "medium", "high"} else "medium"


def _rejected(error: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "accepted": False,
        "source": "hermes_planner_contract",
        "error": error,
        **extra,
    }
