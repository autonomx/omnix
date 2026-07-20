"""Deterministic repair of provider-authored World Forge topic contracts."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from app.rpg.session.genesis.world_forge_generation import (
    GeneratedTopic,
    WorldForgeGenerationResult,
)


def _text(*values: Any) -> str:
    return next((" ".join(str(value).split()) for value in values if str(value or "").strip()), "")


def _long(value: str, minimum: int, fallback: str) -> str:
    resolved = value or fallback
    while len(resolved) < minimum:
        resolved = f"{resolved} {fallback}".strip()
    return resolved


def _list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _row_id(row: Mapping[str, Any], fields: Iterable[str]) -> str:
    return next((_text(row.get(field)) for field in fields if _text(row.get(field))), "")


def _kind(row: Mapping[str, Any], entity_id: str) -> str:
    raw = _text(row.get("kind"), row.get("type")).casefold().replace(" ", "_")
    if entity_id.startswith("loc:") or raw in {"location", "place", "venue", "district"}:
        return "location"
    if entity_id.startswith("npc:") or raw in {"npc", "character", "person"}:
        return "npc"
    if entity_id.startswith("fac:") or raw in {"faction", "organization", "gang", "corporation"}:
        return "faction"
    return raw or "entity"


def _unique_rows(rows: Iterable[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = _text(row.get(field))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def repair_generation_contracts(
    generation: WorldForgeGenerationResult,
    *,
    starting_location: str,
) -> WorldForgeGenerationResult:
    """Normalize common live-provider aliases and remove dangling references."""

    raw_entities = [dict(row) for topic in generation.topics for row in topic.entities]
    entities: list[dict[str, Any]] = []
    for raw in raw_entities:
        entity_id = _row_id(raw, ("id", "entity_id", "location_id", "faction_id", "npc_id"))
        if not entity_id:
            continue
        row = dict(raw)
        row["id"] = entity_id
        row["kind"] = _kind(row, entity_id)
        row["name"] = _text(row.get("name"), row.get("title"), entity_id)
        row.setdefault("visibility", "game_master_canon")
        entities.append(row)
    entities = _unique_rows(entities, "id")
    entity_ids = {str(row["id"]) for row in entities}

    locations = [row for row in entities if row["kind"] == "location"]
    if locations and "region:world" not in entity_ids:
        entities.append(
            {
                "id": "region:world",
                "kind": "region",
                "name": "World Region",
                "description": "The canonical region containing repaired launch locations.",
                "visibility": "game_master_canon",
            }
        )
        entity_ids.add("region:world")
    fallback_location = starting_location if starting_location in entity_ids else (
        str(locations[0]["id"]) if locations else ""
    )

    raw_fact_ids = {
        _row_id(row, ("id", "fact_id", "evidence_id"))
        for topic in generation.topics
        for row in topic.facts
    }
    raw_fact_ids.discard("")
    for row in entities:
        description = _text(row.get("description"), row.get("summary"), row.get("backstory"), row["name"])
        if row["kind"] == "location":
            parent = _text(row.get("region_id"), row.get("realm_id"), row.get("parent_id"))
            row["region_id"] = parent if parent in entity_ids and parent != row["id"] else "region:world"
            row["sensory_profile"] = _long(
                _text(row.get("sensory_profile"), description), 20, f"Distinct sights and sounds define {row['name']}."
            )
            row["dossier_status"] = "complete"
        elif row["kind"] == "npc":
            row["appearance"] = _long(_text(row.get("appearance"), description), 20, f"{row['name']} has a distinctive presence.")
            row["personality"] = _long(_text(row.get("personality"), description), 20, f"{row['name']} acts with deliberate purpose.")
            row["backstory"] = _long(_text(row.get("backstory"), description), 30, f"{row['name']} has a history rooted in this world.")
            row["speech_style"] = _long(_text(row.get("speech_style")), 10, "Direct and distinctive.")
            row["goals"] = _list(row.get("goals")) or [f"Advance {row['name']}'s current objective"]
            row["motives"] = _list(row.get("motives")) or ["Protect personal interests"]
            row["faction_ids"] = [value for value in _list(row.get("faction_ids")) if value in entity_ids]
            row["secrets"] = _list(row.get("secrets"))
            row["known_facts"] = [value for value in _list(row.get("known_facts")) if value in raw_fact_ids]
            location_id = _text(row.get("location_id"))
            if location_id not in entity_ids:
                row["location_id"] = fallback_location
            row["dossier_status"] = "complete"
        elif row["kind"] == "faction":
            row["values"] = _list(row.get("values")) or ["influence"]
            row["goals"] = _list(row.get("goals")) or [f"Expand {row['name']}'s influence"]

        for field in (
            "realm_id",
            "region_id",
            "location_id",
            "parent_id",
            "institution_id",
        ):
            if _text(row.get(field)) not in entity_ids:
                row.pop(field, None)
        for field in ("opposes", "allies", "recruits_from", "worships", "controls", "knows"):
            if field in row:
                row[field] = [value for value in _list(row.get(field)) if value in entity_ids]
        if "faction_ids" in row:
            row["faction_ids"] = [
                value for value in _list(row.get("faction_ids")) if value in entity_ids
            ]

    entity_by_original: dict[str, dict[str, Any]] = {str(row["id"]): row for row in entities}
    assigned_entities: set[str] = set()
    fact_ids: set[str] = set()
    repaired_topics: list[GeneratedTopic] = []
    seen_documents: set[str] = set()
    seen_facts: set[str] = set()
    seen_relationships: set[str] = set()
    seen_rules: set[str] = set()
    seen_threads: set[str] = set()

    for topic_index, topic in enumerate(generation.topics):
        topic_entities: list[dict[str, Any]] = []
        for raw in topic.entities:
            entity_id = _row_id(raw, ("id", "entity_id", "location_id", "faction_id", "npc_id"))
            if entity_id in entity_by_original and entity_id not in assigned_entities:
                topic_entities.append(entity_by_original[entity_id])
                assigned_entities.add(entity_id)
        if topic_index == 0 and "region:world" in entity_by_original:
            topic_entities.append(entity_by_original["region:world"])
            assigned_entities.add("region:world")

        documents: list[dict[str, Any]] = []
        for index, raw in enumerate(topic.documents, start=1):
            row = dict(raw)
            document_id = _row_id(row, ("document_id", "id")) or f"document:{topic.topic_id}:{index}"
            if document_id in seen_documents:
                continue
            seen_documents.add(document_id)
            content = _long(_text(row.get("full_text"), row.get("content"), row.get("summary")), 30, f"Canon material for {topic.topic_id}.")
            row.update(
                {
                    "document_id": document_id,
                    "topic_id": topic.topic_id,
                    "title": _text(row.get("title"), document_id),
                    "full_text": content,
                    "summary_120": _long(_text(row.get("summary_120"), content[:120]), 20, content),
                    "summary_500": _long(_text(row.get("summary_500"), content[:500]), 20, content),
                    "visibility": _text(row.get("visibility"), "game_master_canon"),
                    "entities": [value for value in _list(row.get("entities") or row.get("entity_refs")) if value in entity_ids],
                }
            )
            documents.append(row)

        facts: list[dict[str, Any]] = []
        for index, raw in enumerate(topic.facts, start=1):
            row = dict(raw)
            fact_id = _row_id(row, ("id", "fact_id", "evidence_id")) or f"fact:{topic.topic_id}:{index}"
            if fact_id in seen_facts:
                continue
            seen_facts.add(fact_id)
            refs = [value for value in _list(row.get("entity_refs") or row.get("entities")) if value in entity_ids]
            if not refs and entity_ids:
                refs = [fallback_location or sorted(entity_ids)[0]]
            row.update(
                {
                    "id": fact_id,
                    "content": _long(_text(row.get("content"), row.get("statement"), row.get("object")), 10, f"Canonical fact from {topic.topic_id}."),
                    "authority": "generated_proposal",
                    "approved_authority": "objective_canon",
                    "visibility": _text(row.get("visibility"), "game_master_canon"),
                    "entity_refs": refs,
                }
            )
            facts.append(row)
            fact_ids.add(fact_id)

        relationships: list[dict[str, Any]] = []
        for index, raw in enumerate(topic.relationships, start=1):
            row = dict(raw)
            relationship_id = _row_id(row, ("id", "relationship_id")) or f"relationship:{topic.topic_id}:{index}"
            source = _row_id(row, ("source_id", "source_entity_id"))
            target = _row_id(row, ("target_id", "target_entity_id"))
            if relationship_id in seen_relationships or source not in entity_ids or target not in entity_ids:
                continue
            seen_relationships.add(relationship_id)
            row.update({"id": relationship_id, "source_id": source, "target_id": target})
            relationships.append(row)

        threads: list[dict[str, Any]] = []
        for index, raw in enumerate(topic.story_threads, start=1):
            row = dict(raw)
            thread_id = _row_id(row, ("id", "thread_id")) or f"thread:{topic.topic_id}:{index}"
            if thread_id in seen_threads:
                continue
            seen_threads.add(thread_id)
            locations_for_thread = _list(row.get("location_ids") or row.get("primary_locations"))
            start_ref = _text(row.get("starting_location_ref"))
            if start_ref:
                locations_for_thread.append(start_ref)
            row.update(
                {
                    "id": thread_id,
                    "title": _text(row.get("title"), thread_id),
                    "summary": _long(_text(row.get("summary"), row.get("description")), 20, f"An active story thread for {topic.topic_id}."),
                    "status": _text(row.get("status"), "active"),
                    "actor_ids": [value for value in _list(row.get("actor_ids") or row.get("primary_actors")) if value in entity_ids],
                    "location_ids": [value for value in dict.fromkeys(locations_for_thread) if value in entity_ids],
                    "faction_ids": [value for value in _list(row.get("faction_ids") or row.get("key_factions")) if value in entity_ids],
                }
            )
            threads.append(row)

        rules: list[dict[str, Any]] = []
        for index, raw in enumerate(topic.knowledge_rules, start=1):
            row = dict(raw)
            rule_id = _row_id(row, ("id", "rule_id")) or f"knowledge:{topic.topic_id}:{index}"
            evidence = _row_id(row, ("evidence_id", "fact_id"))
            if rule_id in seen_rules or (evidence and evidence not in raw_fact_ids):
                continue
            seen_rules.add(rule_id)
            row["id"] = rule_id
            if evidence:
                row["evidence_id"] = evidence
            rules.append(row)

        provenance = dict(topic.provenance)
        provenance.setdefault("generator", "world_launch_contract_repair_v1")
        repaired_topics.append(
            replace(
                topic,
                documents=tuple(documents),
                entities=tuple(topic_entities),
                facts=tuple(facts),
                relationships=tuple(relationships),
                knowledge_rules=tuple(rules),
                story_threads=tuple(threads),
                provenance=provenance,
            )
        )

    return replace(generation, topics=tuple(repaired_topics))
