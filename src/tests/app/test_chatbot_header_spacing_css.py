from __future__ import annotations

import re
from pathlib import Path


CSS_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "web"
    / "src"
    / "features"
    / "chatbot"
    / "ChatbotWorkspaceAssistantNav.css"
)


def test_fullscreen_button_has_dedicated_personality_separation() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    rule = re.search(
        r"\.assistant-chat-integrated-actions\s+"
        r"\.assistant-chat-fullscreen-button\s*\{(?P<body>[^}]*)\}",
        css,
        flags=re.S,
    )

    assert rule is not None
    margin = re.search(r"margin-left:\s*(?P<value>[0-9.]+)rem", rule.group("body"))
    assert margin is not None
    assert float(margin.group("value")) >= 1.0
