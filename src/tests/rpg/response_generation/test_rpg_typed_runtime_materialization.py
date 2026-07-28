from __future__ import annotations

import json

import pytest

from app.providers.base import ChatResponse, ProviderConfig
from app.rpg.llm_app_gateway import AppLLMGateway
from app.rpg.session.genesis.runtime_materialization import (
    RuntimeMaterializationProposal,
    _canonicalize_proposal,
    _expected_proposal_validator,
)


def _lore() -> str:
    paragraph = (
        "The echo wolf moves through rain-dark woodland with a silver outline that "
        "fades whenever a traveler looks directly at it. Hunters first notice the "
        "silence of birds and familiar voices repeating beyond the firelight."
    )
    return "\n\n".join([paragraph, paragraph, paragraph, paragraph])


def _payload(*, extra: bool = False) -> dict:
    payload = {
        "kind": "creature",
        "name": "Echo Wolf",
        "lore_text": _lore(),
        "creature": {
            "definition_id": "model-chosen-id",
            "name": "Echo Wolf",
            "level": 4,
            "hp": 38,
            "defense": 14,
            "armor": 2,
            "damage_min": 5,
            "damage_max": 9,
            "accuracy_bonus": 3,
            "initiative_bonus": 4,
            "morale_threshold": 25,
            "tags": ["beast", "echo"],
            "loot_table_id": "loot:echo-wolf",
            "xp_value": 120,
            "budget_cost": 90,
            "condition_immunities": ["prone"],
            "vulnerabilities": [],
            "behavior": "Stalks frightened targets and copies familiar voices.",
            "habitat": "Old bridges and memory-rich woodland.",
        },
        "location": None,
    }
    if extra:
        payload["invented_control_field"] = True
    return payload


class _Provider:
    provider_name = "lmstudio"

    def __init__(self, payloads: list[dict]) -> None:
        self.config = ProviderConfig(provider_type="lmstudio", model="test-model")
        self.payloads = list(payloads)
        self.calls: list[dict] = []

    def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), **kwargs})
        return ChatResponse(
            content=json.dumps(self.payloads.pop(0)),
            model="test-model",
            finish_reason="stop",
        )


def test_app_gateway_returns_validated_runtime_proposal() -> None:
    provider = _Provider([_payload()])
    gateway = AppLLMGateway(provider)

    proposal = gateway.generate_typed(
        "Materialize the creature.",
        output_model=RuntimeMaterializationProposal,
        contract_id="rpg.runtime_materialization.proposal",
        contract_version=2,
        context={"target": {"kind": "creature", "name": "Echo Wolf"}},
        schema_profile="canon_strict",
        semantic_validator=_expected_proposal_validator("creature", "Echo Wolf"),
    )
    canonical = _canonicalize_proposal(
        proposal,
        kind="creature",
        name="Echo Wolf",
    )

    assert canonical.creature is not None
    assert canonical.creature.definition_id == "creature:echo-wolf"
    assert provider.calls[0]["response_format"]["type"] == "json_schema"
    assert gateway.last_structured_diagnostics is not None
    assert gateway.last_structured_diagnostics.contract_version == 2


def test_runtime_contract_rejects_unexpected_control_fields() -> None:
    provider = _Provider([_payload(extra=True)])
    gateway = AppLLMGateway(provider)

    with pytest.raises(Exception, match="schema validation"):
        gateway.generate_typed(
            "Materialize the creature.",
            output_model=RuntimeMaterializationProposal,
            contract_id="rpg.runtime_materialization.proposal",
            contract_version=2,
            max_provider_calls=1,
            max_validation_regenerations=0,
            semantic_validator=_expected_proposal_validator("creature", "Echo Wolf"),
        )
