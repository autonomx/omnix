from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.rpg.session.runtime import apply_turn
from app.rpg.session.service import create_or_normalize_session, save_session
from app.rpg.creator.defaults import apply_adventure_defaults


OUTPUT_PATH = Path("manual_rpg_llm_transcript.txt")


PROMPTS = [
    "I ask Bran for a room to rent",
    "I want a better room. I then punch Bran",
    "I throw Bran to the ground",
    "I then apologize to Bran",
    "I ask Bran how he feels",
    "I ask Bran if he still has a room available",
]


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_narration(result: Dict[str, Any]) -> str:
    # Check direct keys
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in result subdict
    result_sub = _safe_dict(result.get("result"))
    for key in (
        "narration",
        "narrative",
        "text",
        "message",
        "rendered_narration",
        "deterministic_fallback_narration",
    ):
        value = result_sub.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check in session runtime_state
    session = _safe_dict(result.get("session"))
    runtime_state = _safe_dict(session.get("runtime_state"))
    for key in ("last_narration", "last_turn_narration"):
        value = runtime_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Check authoritative
    authoritative = _safe_dict(result.get("authoritative"))
    for key in ("summary", "deterministic_fallback_narration"):
        value = authoritative.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _compact_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def main() -> None:
    os.environ.setdefault("PYTHONPATH", ".")

    # Create and save a test session
    session = create_or_normalize_session({})
    session = apply_adventure_defaults(session)
    session["manifest"] = {"session_id": "manual_test_session"}
    session["runtime_state"]["force_sync_narration"] = True
    save_session(session)
    session_id = "manual_test_session"

    lines: List[str] = []
    lines.append("# Manual RPG LLM Transcript")
    lines.append("")
    lines.append(f"session_id: {session_id}")
    lines.append("")

    for index, prompt in enumerate(PROMPTS, start=1):
        result = apply_turn(session_id, prompt)

        result_sub = _safe_dict(result.get("result"))
        session = _safe_dict(result.get("session") or session)
        runtime_state = _safe_dict(session.get("runtime_state"))

        narration = _extract_narration(result)

        turn_contract = _safe_dict(
            result.get("turn_contract")
            or result_sub.get("turn_contract")
            or runtime_state.get("last_turn_contract")
        )

        lines.append("=" * 80)
        lines.append(f"TURN {index}")
        lines.append(f"PLAYER: {prompt}")
        lines.append("")
        lines.append("NARRATION:")
        lines.append(narration or "[no narration found]")
        lines.append("")
        lines.append("TURN CONTRACT:")
        lines.append(_compact_json(turn_contract))
        lines.append("")
        lines.append("RESULT SUBDICT:")
        lines.append(_compact_json(result_sub))
        lines.append("")
        lines.append("RUNTIME STATE KEYS:")
        lines.append(", ".join(sorted(runtime_state.keys())))
        lines.append("")
        lines.append("RAW RESULT:")
        lines.append(_compact_json(result))
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote transcript to: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()