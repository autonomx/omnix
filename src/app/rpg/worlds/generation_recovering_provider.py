"""Same-model, information-preserving recovery for World Forge responses."""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from pydantic import BaseModel

from app.providers.base import ChatMessage
from app.providers.structured import StructuredContract, StructuredOutputGateway
from app.providers.structured.errors import StructuredOutputError
from app.rpg.session.genesis.world_forge_contract import CampaignTopicNode
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic
from app.rpg.worlds.generation_first_pass_provider import (
    FirstPassWorldForgeTopicGenerator,
    _identity_contract,
    _identity_instruction,
    _strict_profile_contract,
    _strict_topic_contract,
)
from app.rpg.worlds.generation_recovery_registry import StructuredRegistryRecoveryMixin
from app.rpg.worlds.generation_recovery_retained_registry import (
    retained_registry_response,
)
from app.rpg.worlds.generation_recovery_review import StructuredRecoveryReviewMixin
from app.rpg.worlds.generation_structured_recovery import (
    CapturingStructuredProvider,
    decode_candidate,
    deterministic_repair,
    merge_diagnostics,
    recovery_messages,
    retained_topic_response,
    validate_payload,
)
from app.rpg_world_forge_provider import (
    WorldForgeTopicResponse,
    _payload,
    _system_prompt,
    _token_estimate,
)
from app.rpg_world_forge_single_pass_provider import (
    SinglePassWorldForgeProviderError,
    _definitions,
    _field_contract,
    _one_call_budget,
)


@dataclass(frozen=True)
class _RecoveredValue:
    value: BaseModel
    diagnostics: Mapping[str, Any]
    prompt_tokens: int
    completion_tokens: int


class RecoveringFirstPassWorldForgeTopicGenerator(
    StructuredRecoveryReviewMixin,
    StructuredRegistryRecoveryMixin,
    FirstPassWorldForgeTopicGenerator,
):
    """Use the configured model once more only to restructure its own candidate."""

    _recovered_value_type = _RecoveredValue

    def _provider_call(
        self,
        messages: list[ChatMessage],
        *,
        contract: StructuredContract[Any],
        max_tokens: int,
        temperature: float,
    ):
        capture = CapturingStructuredProvider(self.provider)
        gateway = StructuredOutputGateway(capture)
        with self._limiter():
            outcome = gateway.try_generate(
                messages,
                contract=replace(
                    contract,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                model=self.config.model or None,
                retry_budget=_one_call_budget(self.config.timeout_seconds),
            )
        return outcome, capture.raw_text

    def _recover(
        self,
        *,
        contract: StructuredContract[Any],
        outcome: Any,
        raw_text: str,
        original_messages: list[ChatMessage],
        expected_topic_id: str,
        allocated_entity_ids: tuple[str, ...],
        expected_entity_kind: str,
        max_tokens: int,
        retain_invalid_kind: str,
    ) -> _RecoveredValue:
        original_error = outcome.error
        assert isinstance(original_error, Exception)
        if not isinstance(original_error, StructuredOutputError) or not raw_text:
            raise SinglePassWorldForgeProviderError(
                expected_topic_id,
                original_error,
                outcome.diagnostics.as_dict(),
                unit=retain_invalid_kind,
            ) from original_error

        decoded = decode_candidate(raw_text)
        repaired = deterministic_repair(
            decoded,
            expected_topic_id=expected_topic_id,
            allocated_entity_ids=allocated_entity_ids,
            expected_entity_kind=expected_entity_kind,
        )
        value, repair_error = validate_payload(contract, repaired.payload)
        original_prompt_tokens = sum(
            _token_estimate(message.content) for message in original_messages
        )
        original_completion_tokens = _token_estimate(raw_text)
        if value is not None:
            diagnostics = merge_diagnostics(
                outcome.diagnostics.as_dict(),
                None,
                method="deterministic_normalisation",
                repair_codes=repaired.codes,
                raw_text=raw_text,
                error=original_error,
            )
            return _RecoveredValue(
                value,
                diagnostics,
                original_prompt_tokens,
                original_completion_tokens,
            )

        correction_error = repair_error or original_error
        correction_messages = recovery_messages(
            contract=contract,
            raw_text=raw_text,
            decoded_payload=repaired.payload or decoded,
            error=correction_error,
            expected_topic_id=expected_topic_id,
            allocated_entity_ids=allocated_entity_ids,
            expected_entity_kind=expected_entity_kind,
        )
        corrected, corrected_raw = self._provider_call(
            correction_messages,
            contract=contract,
            max_tokens=max_tokens,
            temperature=0.0,
        )
        prompt_tokens = original_prompt_tokens + sum(
            _token_estimate(message.content) for message in correction_messages
        )
        completion_tokens = original_completion_tokens + (
            _token_estimate(corrected_raw) if corrected_raw else 0
        )
        if corrected.error is None and corrected.value is not None:
            diagnostics = merge_diagnostics(
                outcome.diagnostics.as_dict(),
                corrected.diagnostics.as_dict(),
                method="same_model_extraction",
                repair_codes=repaired.codes,
                raw_text=raw_text,
                error=original_error,
            )
            return _RecoveredValue(
                corrected.value,
                diagnostics,
                prompt_tokens,
                completion_tokens,
            )

        final_error = corrected.error or correction_error
        if retain_invalid_kind == "registry":
            retained = retained_registry_response(
                expected_topic_id=expected_topic_id,
                allocated_entity_ids=allocated_entity_ids,
                decoded_payload=repaired.payload or decoded,
                raw_text=raw_text,
                error=final_error,
            )
            method = "retained_invalid_registry"
        elif retain_invalid_kind == "topic":
            retained = retained_topic_response(
                expected_topic_id=expected_topic_id,
                decoded_payload=repaired.payload or decoded,
                raw_text=raw_text,
                error=final_error,
            )
            method = "retained_invalid_candidate"
        else:
            diagnostics = merge_diagnostics(
                outcome.diagnostics.as_dict(),
                corrected.diagnostics.as_dict(),
                method="same_model_extraction_failed",
                repair_codes=repaired.codes,
                raw_text=raw_text,
                error=final_error,
            )
            raise SinglePassWorldForgeProviderError(
                expected_topic_id,
                final_error,
                diagnostics,
                unit=retain_invalid_kind,
            ) from final_error
        diagnostics = merge_diagnostics(
            outcome.diagnostics.as_dict(),
            corrected.diagnostics.as_dict(),
            method=method,
            repair_codes=repaired.codes,
            raw_text=raw_text,
            error=final_error,
        )
        return _RecoveredValue(
            retained,
            diagnostics,
            prompt_tokens,
            completion_tokens,
        )

    def _generate_response(
        self,
        node: CampaignTopicNode,
        *,
        seed: int,
        campaign_context: Mapping[str, Any],
        dependency_topics: Mapping[str, GeneratedTopic],
        expected_entity_count: int | None = None,
        expected_entity_ids: tuple[str, ...] = (),
        expected_entity_names: tuple[str, ...] = (),
        batch_index: int | None = None,
        batch_count: int | None = None,
        existing_entities: tuple[Mapping[str, str], ...] = (),
        assigned_entity_ids: tuple[str, ...] = (),
        assigned_entities: tuple[Mapping[str, str], ...] = (),
    ) -> tuple[WorldForgeTopicResponse, Mapping[str, Any], int, int]:
        count = expected_entity_count or node.target_count
        ids = expected_entity_ids or self._assigned_entity_ids(
            node,
            batch_index=batch_index or 0,
            requested_count=count,
        )
        index = batch_index if batch_index is not None else 0
        total = batch_count if batch_count is not None else 1
        prompt = _system_prompt(
            node,
            batch_index=index,
            batch_count=total,
            existing_entities=existing_entities,
            assigned_entity_ids=ids,
            assigned_entities=assigned_entities,
        ) + (
            " PROFILE_FIELD_CONTRACT is authoritative. Use the exact allocated ID "
            "and entity kind, include all required top-level fields, obey declared "
            "JSON types, and use only listed reference IDs. Unknown fields are forbidden."
        ) + _identity_instruction(node.topic_id, ids)
        request = _payload(
            node,
            seed=seed,
            campaign_context=campaign_context,
            dependency_topics=dependency_topics,
            batch_index=index,
            batch_count=total,
            existing_entities=existing_entities,
            assigned_entity_ids=ids,
            assigned_entities=assigned_entities,
        )
        request["required_output"]["identity_contract"] = _identity_contract(
            node.topic_id,
            ids,
        )
        request["required_output"]["profile_field_contract"] = _field_contract(
            node,
            allocated_ids=ids,
            dependencies=dependency_topics,
        )
        messages = [
            ChatMessage(role="system", content=prompt),
            ChatMessage(
                role="user",
                content=json.dumps(request, ensure_ascii=False, sort_keys=True),
            ),
        ]
        contract = (
            _strict_profile_contract(
                node,
                expected_count=count,
                expected_ids=ids,
                expected_names=expected_entity_names,
                dependencies=dependency_topics,
            )
            if _definitions(node)
            else _strict_topic_contract(
                node.topic_id,
                expected_entity_count=count,
                expected_entity_ids=ids,
                expected_entity_names=expected_entity_names,
            )
        )
        outcome, raw_text = self._provider_call(
            messages,
            contract=contract,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        if outcome.error is None and outcome.value is not None:
            recovered = _RecoveredValue(
                outcome.value,
                outcome.diagnostics.as_dict(),
                sum(_token_estimate(message.content) for message in messages),
                _token_estimate(raw_text),
            )
        else:
            recovered = self._recover(
                contract=contract,
                outcome=outcome,
                raw_text=raw_text,
                original_messages=messages,
                expected_topic_id=node.topic_id,
                allocated_entity_ids=ids,
                expected_entity_kind=str(
                    node.metadata.get("entity_kind") or node.topic_id
                ),
                max_tokens=self.config.max_tokens,
                retain_invalid_kind="topic",
            )
        value = recovered.value
        assert isinstance(value, WorldForgeTopicResponse)
        method = str(
            dict(recovered.diagnostics.get("structured_recovery") or {}).get("method")
            or ""
        )
        if method != "retained_invalid_candidate":
            value = self._apply_registry_slots(value, assigned_entities)
        return (
            value,
            recovered.diagnostics,
            recovered.prompt_tokens,
            recovered.completion_tokens,
        )


__all__ = ["RecoveringFirstPassWorldForgeTopicGenerator"]
