"""The scene lore a campaign writes when no model answers (``runtime_lore_materialization``): a place's and an entity's
bundle, chosen deterministically from the campaign and the entity, so the same campaign always writes the same lore."""
from __future__ import annotations

import hashlib
from typing import Any

from .campaign_lore_store import _text
from .runtime_lore_materialization import SceneLoreTarget, _name_from_id, _slug, canonical_lore_topic_id
from .world_forge_dossiers import project_entity_dossier, validate_entity_dossier


def _stable_choices(
    campaign_id: str,
    entity_id: str,
) -> tuple[str, str, str, str]:
    digest = hashlib.sha256(f"{campaign_id}|{entity_id}".encode()).digest()
    names = (
        "Mara Venn",
        "Tomas Reed",
        "Elian Ward",
        "Nessa Vale",
        "Corin Ash",
        "Sera Holt",
    )
    roles = (
        "innkeeper",
        "market steward",
        "local healer",
        "watch sergeant",
        "scribe",
        "stable master",
    )
    traits = (
        "practical and observant",
        "warm but guarded",
        "direct and civic-minded",
        "patient and meticulous",
    )
    histories = (
        "an old trade crossing",
        "a refuge founded after a border war",
        "a river settlement grown around a shrine",
        "a fortified market built over older ruins",
    )
    return (
        names[digest[0] % len(names)],
        roles[digest[1] % len(roles)],
        traits[digest[2] % len(traits)],
        histories[digest[3] % len(histories)],
    )


def fallback_location_bundle(
    campaign_id: str,
    target: SceneLoreTarget,
) -> dict[str, Any]:
    first = _stable_choices(campaign_id, target.entity_id)
    second = _stable_choices(campaign_id, target.entity_id + ":2")
    overview = (
        f"{target.name} is a lived-in settlement shaped by its roads, trades, "
        "and surrounding region. Its streets join a practical civic center, "
        "clustered homes, workshops, and public gathering places. The settlement "
        "has an established daily rhythm and recognizable local customs."
    )
    history = (
        f"Local tradition describes {target.name} as {first[3]}. Its institutions "
        "grew from the need to protect travelers, settle disputes, preserve supplies, "
        "and maintain links with neighboring communities."
    )
    npcs = []
    for index, choice in enumerate((first, second), start=1):
        name, role, traits, _ = choice
        npc_id = f"npc:{_slug(target.name)}:{index}:{_slug(name)}"
        npcs.append(
            {
                "id": npc_id,
                "kind": "npc",
                "name": name,
                "role": role,
                "description": (
                    f"{name} is a {role} in {target.name}, known publicly as {traits}."
                ),
                "personality": traits,
                "speech_style": "plainspoken and locally informed",
                "location_id": target.entity_id,
                "visibility": "public",
                "dossier_status": "materialized",
            }
        )
    documents = [
        {
            "title": target.name,
            "topic_id": "locations",
            "full_text": overview,
            "entity_refs": [target.entity_id],
        },
        {
            "title": f"History of {target.name}",
            "topic_id": "history",
            "full_text": history,
            "entity_refs": [target.entity_id],
        },
    ]
    documents.extend(
        {
            "title": npc["name"],
            "topic_id": "npcs",
            "full_text": npc["description"],
            "entity_refs": [npc["id"], target.entity_id],
        }
        for npc in npcs
    )
    return {
        "entities": [
            {
                "id": target.entity_id,
                "kind": "location",
                "name": target.name,
                "description": overview,
                "sensory_profile": (
                    "Work and conversation mix with weathered stone, timber, "
                    "cooking smoke, and road dust."
                ),
                "services": ["lodging", "food", "trade", "local guidance"],
                "landmarks": [
                    "central gathering place",
                    "market street",
                    "local watch post",
                ],
                "inhabitants": [row["id"] for row in npcs],
                "visibility": "public",
                "dossier_status": "materialized",
            },
            *npcs,
        ],
        "documents": documents,
        "facts": [
            {
                "id": f"fact:{_slug(target.name)}:settlement",
                "content": overview,
                "entity_refs": [target.entity_id],
            },
            {
                "id": f"fact:{_slug(target.name)}:history",
                "content": history,
                "entity_refs": [target.entity_id],
            },
        ],
        "relationships": [
            {
                "id": f"relationship:{_slug(target.name)}:{index}",
                "kind": "located_in",
                "source_id": npc["id"],
                "target_id": target.entity_id,
                "content": f"{npc['name']} lives and works in {target.name}.",
                "entity_refs": [npc["id"], target.entity_id],
            }
            for index, npc in enumerate(npcs, start=1)
        ],
    }


def fallback_entity_bundle(target: SceneLoreTarget, location_name: str = "") -> dict[str, Any]:
    kind = target.kind if target.kind != "entity" else "creature"
    if kind == "npc":
        description = (
            f"{target.name} is a person currently encountered in the campaign, "
            "with a public identity grounded in the surrounding community."
        )
    elif kind in {"monster", "creature"}:
        description = (
            f"{target.name} is a known {kind} of this region. Its visible anatomy, "
            "movement, habitat, and behavior define how witnesses recognize it "
            "without revealing unobserved abilities or hidden weaknesses."
        )
    else:
        description = (
            f"{target.name} is an established {kind} in the campaign world, "
            "described through public and presently observable facts."
        )
    entity: dict[str, Any] = {
        "id": target.entity_id,
        "kind": kind,
        "name": target.name,
        "description": description,
        "location_id": target.location_id,
        "visibility": "player_known",
        "dossier_status": "materialized",
    }
    if kind in {"monster", "creature"}:
        entity.update(
            {
                "appearance": "Distinctive enough to identify at close range.",
                "behavior": "Acts according to its habitat, needs, and circumstances.",
                "habitat": target.location_id,
            }
        )
    elif kind == "npc":
        entity.update(
            {
                "appearance": (
                    "Their clothing, posture, and working gear reflect their place "
                    "in the surrounding community."
                ),
                "personality": (
                    "Observant and guarded with strangers, but responsive to direct "
                    "questions and changes in the local situation."
                ),
                "backstory": (
                    f"{target.name} has established ties to the people and routines "
                    f"around {_name_from_id(target.location_id) if target.location_id else 'this region'}."
                ),
                "speech_style": (
                    "Speaks naturally and specifically, using local knowledge and "
                    "avoiding claims beyond what they know."
                ),
                "goals": ["Protect their livelihood and standing in the community."],
                "motives": ["Respond to immediate pressures without exposing private knowledge."],
                "relationships": [],
                "known_facts": [],
                "current_situation": (
                    f"Currently encountered at {_name_from_id(target.location_id)}."
                    if target.location_id
                    else "Currently present in the active scene."
                ),
                "dossier_status": "complete",
            }
        )
        short_summary, dossier = project_entity_dossier(
            entity,
            card_type="npcs",
            entity_id=target.entity_id,
        )
        entity["short_summary"] = short_summary
        entity["dossier"] = dossier
    elif kind not in {"monster", "creature"}:
        entity.update(
            {
                "summary": description,
                "current_situation": "Known through the active campaign.",
            }
        )
    short_summary, dossier = project_entity_dossier(
        entity,
        card_type=canonical_lore_topic_id(kind),
        entity_id=target.entity_id,
    )
    entity["short_summary"] = _text(entity.get("short_summary")) or short_summary
    if validate_entity_dossier(entity.get("dossier")):
        entity["dossier"] = dossier
    return {
        "entities": [entity],
        "documents": [
            {
                "title": target.name,
                "topic_id": canonical_lore_topic_id(kind),
                "full_text": description,
                "entity_refs": [target.entity_id],
            }
        ],
        "facts": [
            {
                "id": f"fact:{_slug(target.entity_id)}:identity",
                "content": description,
                "entity_refs": [target.entity_id],
            }
        ],
        "relationships": (
            [
                {
                    "id": f"relationship:{_slug(target.entity_id)}:location",
                    "kind": "encountered_at",
                    "source_id": target.entity_id,
                    "target_id": target.location_id,
                    "content": f"{target.name} was encountered at {location_name or _name_from_id(target.location_id)}.",
                    "entity_refs": [target.entity_id, target.location_id],
                }
            ]
            if target.location_id
            else []
        ),
    }


__all__ = ["fallback_entity_bundle", "fallback_location_bundle"]
