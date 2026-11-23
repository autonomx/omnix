"""Fact-bound presentation projection for causal-link entities."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from .world_forge_generation import GeneratedTopic
from app.apps.rpg.foundation.safe_values import collapsed_text


def project_causal_link_presentations(topic: GeneratedTopic) -> GeneratedTopic:
    """Attach a compact causal card using only canonical structured fields."""

    if topic.topic_id != "causal_links":
        return topic
    entities: list[dict[str, Any]] = []
    for entity in topic.entities:
        row = dict(entity)
        causes = [str(value) for value in row.get("cause_event_ids") or () if str(value)]
        effect_id = collapsed_text(row.get("effect_id"))
        effect_type = collapsed_text(row.get("effect_type"))
        mechanism = collapsed_text(row.get("mechanism"))
        persistence = collapsed_text(row.get("persistence"))
        start_year = row.get("start_year")
        end_year = row.get("end_year")
        row["causal_presentation"] = {
            "cause_event_ids": causes,
            "effect_id": effect_id,
            "effect_type": effect_type,
            "mechanism": mechanism,
            "persistence": persistence,
            "start_year": start_year,
            "end_year": end_year,
        }
        row["short_summary"] = (
            f"{effect_type.replace('_', ' ').title()}: {mechanism} "
            f"Persistence: {persistence}."
        ).strip()
        entities.append(row)
    return replace(
        topic,
        entities=tuple(entities),
        provenance={
            **dict(topic.provenance),
            "causal_presentation_contract": "rpg_causal_link_card_v1",
            "causal_presentation_source": "structured_fields_only",
        },
    )


__all__ = ["project_causal_link_presentations"]
