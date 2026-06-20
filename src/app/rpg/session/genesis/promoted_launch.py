"""Launch current wizard payloads through the Campaign Genesis pipeline."""

from __future__ import annotations

from typing import Any

from .bootstrap import bootstrap_session_from_compiled_genesis
from .compiler import compile_campaign_genesis
from .legacy_adapter import (
    adapt_genesis_payload_to_new_game_payload,
    attach_genesis_to_created_session,
)
from .pipeline_adapter import attach_compiled_genesis_to_session
from .request_promoter import promote_new_game_request_to_genesis


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def create_promoted_new_game(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _safe_dict(payload.get("request") or payload)
    contract = promote_new_game_request_to_genesis(raw)
    legacy = adapt_genesis_payload_to_new_game_payload(
        {"request": {"genesis": contract.model_dump(mode="json")}}
    )
    compiled = compile_campaign_genesis(contract)
    bootstrap = bootstrap_session_from_compiled_genesis(compiled)

    from app.rpg.session.new_game import RpgNewGameRequest, create_new_game_session

    result = create_new_game_session(RpgNewGameRequest.model_validate(legacy))
    result = attach_genesis_to_created_session(result, contract)
    return attach_compiled_genesis_to_session(result, compiled, bootstrap)
