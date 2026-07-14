"""Delivery strategies for one already-approved canonical response."""
from __future__ import annotations

from dataclasses import replace

from .authority import DeliveryMode
from .contracts import CanonicalNarrativeResponse, DeliveryMetadata


class NarrativeDeliveryCoordinator:
    """Deliver the same content immediately or later without regenerating prose."""

    def prepare(
        self,
        response: CanonicalNarrativeResponse,
        mode: DeliveryMode,
    ) -> CanonicalNarrativeResponse:
        response = response.with_content_hash()
        status = "complete" if mode is DeliveryMode.BLOCKING else "pending"
        delivered = tuple(block.block_id for block in response.blocks) if status == "complete" else ()
        return replace(
            response,
            delivery=DeliveryMetadata(
                mode=mode,
                status=status,
                delivered_block_ids=delivered,
            ),
        )

    def complete_deferred(self, response: CanonicalNarrativeResponse) -> CanonicalNarrativeResponse:
        response = response.with_content_hash()
        return replace(
            response,
            delivery=DeliveryMetadata(
                mode=DeliveryMode.DEFERRED,
                status="complete",
                delivered_block_ids=tuple(block.block_id for block in response.blocks),
            ),
        )
