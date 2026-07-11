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
        rollout = (
            result.get("canonical_response", {}).get("rollout", {})
            if isinstance(result.get("canonical_response"), Mapping)
            else {}
        )
        if not bool(rollout.get("publishes_canonical")):
            legacy_visible = str(legacy_payload.get("legacy_visible_text") or "").strip()
            if legacy_visible:
                result["narration"] = legacy_visible
        return result


__all__ = ["StrictRpgProductionResponsePipeline"]
