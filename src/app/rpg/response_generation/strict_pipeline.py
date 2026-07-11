from __future__ import annotations

from typing import Any, Mapping

from .production_pipeline import RpgProductionResponsePipeline
from .strict_proposal_policy import StrictProposalPolicy


class StrictRpgProductionResponsePipeline(RpgProductionResponsePipeline):
    """Production-safe pipeline with fail-closed proposals and exact shadow output."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("proposal_policy", StrictProposalPolicy())
        super().__init__(**kwargs)

    def finalize_payload(
        self,
        legacy_payload: Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = super().finalize_payload(legacy_payload, **kwargs)
        canonical = (
            result.get("canonical_response", {})
            if isinstance(result.get("canonical_response"), Mapping)
            else {}
        )
        rollout = (
            canonical.get("rollout", {})
            if isinstance(canonical.get("rollout"), Mapping)
            else {}
        )
        if isinstance(canonical, dict):
            metadata = (
                canonical.get("metadata", {})
                if isinstance(canonical.get("metadata"), Mapping)
                else {}
            )
            intent = (
                metadata.get("intent_analysis", {})
                if isinstance(metadata.get("intent_analysis"), Mapping)
                else {}
            )
            selected = (
                intent.get("selected", {})
                if isinstance(intent.get("selected"), Mapping)
                else {}
            )
            canonical["developer_trace"] = {
                "trace_version": "rpg_response_trace_v1",
                "turn_id": str(metadata.get("turn_id") or ""),
                "raw_player_input": str(kwargs.get("player_input") or ""),
                "interpreted_intents": [
                    dict(selected),
                    *[
                        dict(row)
                        for row in intent.get("alternatives", ())
                        if isinstance(row, Mapping)
                    ],
                ],
                "selected_affordance": str(selected.get("affordance") or ""),
                "resolver_result": {
                    "mechanic_resolved": bool(
                        kwargs.get("authoritative_turn_result", {}).get("mechanic_resolved")
                        if isinstance(kwargs.get("authoritative_turn_result"), Mapping)
                        else False
                    )
                },
                "retrieval_sources": list(
                    metadata.get("retrieval", {}).get("evidence", ())
                    if isinstance(metadata.get("retrieval"), Mapping)
                    else ()
                ),
                "visibility_decisions": [
                    {"evidence_id": evidence_id, "decision": "excluded_hidden"}
                    for evidence_id in (
                        metadata.get("retrieval", {}).get("hidden_evidence_ids", ())
                        if isinstance(metadata.get("retrieval"), Mapping)
                        else ()
                    )
                ],
                "hermes": dict(metadata.get("hermes") or {}),
                "recovery_plan": dict(metadata.get("recovery_plan") or {}),
                "claim_ledger": dict(metadata.get("claim_ledger") or {}),
                "hard_gates": [
                    dict(row)
                    for row in metadata.get("hard_gate_decisions", ())
                    if isinstance(row, Mapping)
                ],
                "candidate_ranking": [
                    {"candidate_id": candidate_id, "rank": index}
                    for index, candidate_id in enumerate(
                        metadata.get("ranked_candidate_ids", ()),
                        1,
                    )
                ],
                "quality": dict(canonical.get("quality_report") or {}),
                "response_mode": str(canonical.get("mode") or ""),
                "truth_records": list(metadata.get("truth_records") or ()),
                "profile": dict(metadata.get("response_profile") or {}),
                "rollout": dict(rollout),
                "final_visible_response": str(canonical.get("text") or ""),
            }
            result["canonical_response"] = canonical
        if not bool(rollout.get("publishes_canonical")):
            legacy_visible = str(legacy_payload.get("legacy_visible_text") or "").strip()
            if legacy_visible:
                result["narration"] = legacy_visible
        return result


__all__ = ["StrictRpgProductionResponsePipeline"]
