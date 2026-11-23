"""Pure submission policy for durable RPG turn jobs."""
from __future__ import annotations

from typing import Any

from app.jobs.models import CreateJobRequest
from app.persistence.tenant import LOCAL_USER_ID
from app.apps.rpg.foundation.safe_values import stripped_text

RPG_TURN_JOB_TYPE = "rpg.turn"


def rpg_turn_submission_policy(request: CreateJobRequest) -> CreateJobRequest:
    """Normalize legacy ownership and attach a stable idempotency identity."""
    owner_id = stripped_text(request.owner_id)
    compat = _dict_value(request.compat)
    if owner_id and not owner_id.startswith("user:"):
        compat.setdefault("subject_owner_id", owner_id)
        request = request.model_copy(update={"owner_id": LOCAL_USER_ID})

    if request.type != RPG_TURN_JOB_TYPE:
        return request.model_copy(update={"compat": compat})

    payload = _dict_value(request.input_payload)
    input_ref = _dict_value(request.input_ref)
    session_id = stripped_text(input_ref.get("session_id"))
    submission_id = stripped_text(payload.get("submission_id"))
    if session_id and submission_id:
        compat.setdefault(
            "idempotency_key",
            f"rpg-turn:{session_id}:{submission_id}",
        )
    return request.model_copy(update={"compat": compat})


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


