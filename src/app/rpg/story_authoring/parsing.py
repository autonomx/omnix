from __future__ import annotations

import json
from typing import Any, Dict


def parse_story_authoring_json(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return {
            "ok": True,
            "proposal": raw,
            "error": "",
        }
    if raw is None:
        return {
            "ok": False,
            "proposal": {},
            "error": "empty_llm_response",
        }
    text = str(raw).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except Exception as exc:
        return {
            "ok": False,
            "proposal": {},
            "error": f"invalid_json:{type(exc).__name__}:{exc}",
            "raw": str(raw)[:4000],
        }
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "proposal": {},
            "error": f"json_root_not_object:{type(parsed).__name__}",
            "raw": str(raw)[:4000],
        }
    return {
        "ok": True,
        "proposal": parsed,
        "error": "",
        "raw": str(raw)[:4000],
    }