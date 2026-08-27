from __future__ import annotations

from app.agent_runtime import chat_bridge


def test_agent_steering_identity_uses_stable_sha256_not_process_hash() -> None:
    source = open(chat_bridge.__file__, encoding="utf-8").read()
    assert "hashlib.sha256" in source
    assert "hash(normalized)" not in source
