from __future__ import annotations

from app.platform.agent_runtime import chat_lane_agent


def test_agent_steering_identity_uses_stable_sha256_not_process_hash() -> None:
    source = open(chat_lane_agent.__file__, encoding="utf-8").read()
    assert "hashlib.sha256" in source
    assert "hash(normalized)" not in source
