from __future__ import annotations

import json

from app.rpg.performance_trace import build_traced_json_response
from app.rpg.presentation.turn_response import (
    TURN_RESPONSE_CONTRACT_VERSION,
    TURN_RESPONSE_MAX_BYTES,
    build_turn_response_v2,
    turn_response_size_bytes,
)
from app.rpg.presentation.turn_response_budget import enforce_turn_response_budget


def test_oversized_visible_response_is_compacted_below_runtime_limit() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "submission_id": "submit:oversized",
            "interaction_id": "interaction:oversized",
            "turn_id": "turn:oversized",
            "stateful": False,
            "action_type": "npc_interpretive_dialogue",
            "final_narration": "Bran studies the room. " * 12_000,
            "npc": {
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "line": "Business remains steady despite the road. " * 12_000,
            },
        },
        session_id="session:oversized",
        command="I ask Bran how business is doing.",
    )

    assert payload["contract_version"] == TURN_RESPONSE_CONTRACT_VERSION
    assert payload["submission_id"] == "submit:oversized"
    assert payload["interaction_id"] == "interaction:oversized"
    assert payload["response_budget"]["compacted"] is True
    assert payload["visible_response"]["plain_text"]
    assert turn_response_size_bytes(payload) <= TURN_RESPONSE_MAX_BYTES


def test_final_json_boundary_rechecks_budget_after_payload_mutation() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "interaction_id": "interaction:encode",
            "narration": "Bran nods.",
        },
        session_id="session:encode",
        command="I greet Bran.",
    )
    payload["late_private_diagnostic"] = "x" * 250_000

    response = build_traced_json_response(payload)
    encoded = bytes(response.body)
    decoded = json.loads(encoded)

    assert len(encoded) <= TURN_RESPONSE_MAX_BYTES
    assert decoded["contract_version"] == TURN_RESPONSE_CONTRACT_VERSION
    assert decoded["interaction_id"] == "interaction:encode"
    assert decoded["response_budget"]["compacted"] is True
    assert decoded["response_budget"]["fallback"] is True
    assert "late_private_diagnostic" not in decoded


def test_budget_counts_utf8_bytes_not_only_characters() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "interaction_id": "interaction:utf8",
            "narration": "🔥" * 100_000,
        },
        session_id="session:utf8",
        command="I watch the fire.",
    )

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(encoded) <= TURN_RESPONSE_MAX_BYTES
    assert payload["visible_response"]["plain_text"].encode("utf-8")


def test_normal_response_is_not_rewritten_or_marked_compacted() -> None:
    payload = build_turn_response_v2(
        {
            "ok": True,
            "interaction_id": "interaction:normal",
            "narration": "Bran sets down the polishing rag.",
            "npc": {
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "line": "Business is steady enough today.",
            },
        },
        session_id="session:normal",
        command="I ask Bran about business.",
    )

    assert "response_budget" not in payload
    assert payload["response"] == (
        "Bran sets down the polishing rag.\n\n"
        'Bran: "Business is steady enough today."'
    )


def test_adversarial_contract_fields_still_have_an_absolute_fallback() -> None:
    huge = "界" * 200_000
    payload = {
        "ok": True,
        "contract_version": TURN_RESPONSE_CONTRACT_VERSION,
        "session_id": huge,
        "submission_id": huge,
        "interaction_id": huge,
        "turn_id": huge,
        "command": huge,
        "visible_response": {
            "format_version": "rpg_visible_response_v1",
            "narration": huge,
            "messages": [
                {
                    "kind": "npc_dialogue",
                    "speaker_id": huge,
                    "speaker": huge,
                    "text": huge,
                }
                for _ in range(100)
            ],
            "plain_text": huge,
        },
        "response": huge,
        "content": huge,
        "unknown": {"nested": huge},
    }

    bounded = enforce_turn_response_budget(
        payload,
        max_bytes=TURN_RESPONSE_MAX_BYTES,
    )

    assert turn_response_size_bytes(bounded) <= TURN_RESPONSE_MAX_BYTES
    assert bounded["contract_version"] == TURN_RESPONSE_CONTRACT_VERSION
    assert bounded["visible_response"]["plain_text"]
    assert bounded["response_budget"]["compacted"] is True
