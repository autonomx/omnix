"""Voice and live voice share one speech contract (PA-3.3)."""
from __future__ import annotations

import ast
from pathlib import Path

from app.runtime.feature_catalog import load_feature

PLATFORM = Path(__file__).resolve().parents[2] / "app" / "platform"
SPEECH = {"voice": "voice", "live_voice": "live-voice"}


def test_speech_modules_reach_each_other_and_chat_only_through_contracts() -> None:
    reached: set[str] = set()
    for package in SPEECH:
        files = list((PLATFORM / package).rglob("*.py"))
        assert files, package
        for path in files:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app.platform."):
                    target = node.module.split(".")[2]
                    if target != package and (target in SPEECH or target == "chat"):
                        reached.add(node.module)

    assert reached <= {"app.platform.voice.contracts", "app.platform.chat.contracts"}
    assert load_feature("live-voice").uses == ("voice",)
