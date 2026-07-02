from __future__ import annotations

from typing import Any


def hermes_rpg_intent_guard(bundle: dict[str, Any]) -> dict[str, Any]:
    card = bundle.get("card") if isinstance(bundle.get("card"), dict) else {}
    command = str(card.get("command_text") or "").strip()
    ok = bundle.get("ok") is True and bool(command)
    return {
        "ok": ok,
        "source": "hermes_rpg_intent_guard",
        "command_text": command,
        "requires_user_approval": True,
        "armed": False,
        "state_changed": False,
    }
