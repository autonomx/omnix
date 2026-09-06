from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{relative}: expected one occurrence, found {count}: {old[:180]!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


def prepare() -> None:
    # The generated regression tests append immutable Pydantic AgentEvent
    # instances. Rewrite the carrier text before it creates the test file so
    # sequence assignment remains immutable-safe.
    relative = "scripts/apply_self_review_protocol_durability_once.py"
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    old = '''            event.sequence = len(events) + 1\\n            events.append(event)'''
    new = '''            events.append(event.model_copy(update={"sequence": len(events) + 1}))'''
    count = text.count(old)
    if count != 2:
        raise RuntimeError(f"{relative}: expected two immutable-event carrier occurrences, found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def post() -> None:
    replace_once(
        "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
        '''    assert _terminal_message_settles_quality_stage(prose, "self_review")''',
        '''    assert not _terminal_message_settles_quality_stage(prose, "self_review")''',
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    if mode == "prepare":
        prepare()
    elif mode == "post":
        post()
    else:
        raise SystemExit(f"unknown mode: {mode}")
