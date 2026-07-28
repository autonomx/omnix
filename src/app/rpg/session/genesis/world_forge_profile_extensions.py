"""Late-roadmap additive fields for validated World Forge profiles."""
from __future__ import annotations

from .world_forge_profiles import FieldDefinition


def _field(
    field_id: str,
    value_type: str = "string",
    *,
    required: bool = False,
    targets: tuple[str, ...] = (),
    role: str = "",
    description: str = "",
) -> FieldDefinition:
    return FieldDefinition(
        field_id=field_id,
        value_type=value_type,  # type: ignore[arg-type]
        required=required,
        allowed_target_domains=targets,
        semantic_role=role,
        description=description,
    )


def extension_fields(domain_id: str) -> tuple[FieldDefinition, ...]:
    if domain_id == "groups":
        return (
            _field(
                "information_anchor_place_id",
                "entity_ref",
                required=True,
                targets=("places",),
                role="information_anchor",
                description="Canonical place from which this group evaluates information latency.",
            ),
            _field(
                "information_place_ids",
                "entity_ref_list",
                required=True,
                targets=("places",),
                role="information_reach",
                description="Canonical places within the group's direct, regularly updated information reach.",
            ),
            _field(
                "information_locality_signature",
                "structured_object",
                required=True,
                role="information_locality_signature",
                description="Bounded channel, latency, verification, distortion, interception, blackout, cadence, and confidence-decay profile.",
            ),
        )
    return ()


__all__ = ["extension_fields"]
