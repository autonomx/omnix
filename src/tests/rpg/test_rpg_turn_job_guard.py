from __future__ import annotations

from app.jobs.handlers import registry_from_features
from app.jobs.models import CreateJobRequest, ResourceClass
from app.rpg.jobs.turn_executor import _rpg_turn_visible_text
from app.rpg.presentation.visible_response import visible_response_text
from app.runtime.feature_catalog import load_feature


def _request(submission_id: str, command: str) -> CreateJobRequest:
    return CreateJobRequest(
        module="rpg",
        type="rpg.turn",
        resource_class=ResourceClass.CPU,
        input_ref={"session_id": "session-1"},
        input_payload={"command": command, "submission_id": submission_id},
    )


def test_same_rpg_turn_submission_has_stable_idempotency_identity() -> None:
    registry = registry_from_features((load_feature("rpg"),))
    request = _request("submission-1", "I ask Bran how his day is going")

    first = registry.validate_submission(request)
    second = registry.validate_submission(request)

    assert first.compat["idempotency_key"] == "rpg-turn:session-1:submission-1"
    assert second.compat["idempotency_key"] == first.compat["idempotency_key"]
    assert first.resource_class == ResourceClass.GPU_LLM


def test_distinct_rpg_turn_submissions_have_distinct_idempotency_identities() -> None:
    registry = registry_from_features((load_feature("rpg"),))
    first = registry.validate_submission(_request("submission-1", "I ask Bran how his day is going"))
    second = registry.validate_submission(_request("submission-2", "I ask Bran how business is going"))

    assert first.compat["idempotency_key"] != second.compat["idempotency_key"]


def test_rpg_turn_visible_text_uses_shared_formatter() -> None:
    result = {
        "visible_response": {
            "narration": "Bran: It's been a fairly steady day, actually.",
            "npc": {"speaker": "Bran", "line": "It's been a fairly steady day, actually."},
        }
    }

    assert _rpg_turn_visible_text(result) == visible_response_text(result)
