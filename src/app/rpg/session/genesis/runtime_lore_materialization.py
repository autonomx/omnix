"""Materialize missing scene canon before turn-time narrative retrieval."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.rpg.llm_app_gateway import build_app_llm_gateway

from .campaign_lore_store import _mapping, _rows, _text, current_location_identity

_VISIBLE = {"public", "player_known", "learned", "partially_known", "disputed"}
_KIND_PREFIXES = {
    "npc": "npc",
    "character": "npc",
    "creature": "creature",
    "monster": "monster",
    "beast": "creature",
    "location": "location",
    "settlement": "location",
    "town": "location",
    "city": "location",
    "region": "region",
    "faction": "faction",
}
_SCENE_LIST_KEYS = (
    "present_npcs",
    "nearby_npcs",
    "npcs",
    "present_creatures",
    "nearby_creatures",
    "creatures",
    "present_monsters",
    "nearby_monsters",
    "monsters",
    "entities",
    "actors",
)
_SCENE_ID_KEYS = (
    "present_npc_ids",
    "nearby_npc_ids",
    "present_creature_ids",
    "nearby_creature_ids",
    "present_monster_ids",
    "nearby_monster_ids",
    "entity_ids",
    "actor_ids",
)


@dataclass(frozen=True)
class SceneLoreTarget:
    entity_id: str
    kind: str
    name: str
    location_id: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "entity_id": self.entity_id,
            "kind": self.kind,
            "name": self.name,
            "location_id": self.location_id,
        }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unknown"


def _name_from_id(entity_id: str) -> str:
    token = entity_id.split(":", 1)[-1]
    return token.replace("_", " ").replace("-", " ").title() or "Unknown Entity"


def _kind(entity_id: str, value: Mapping[str, Any] | None = None) -> str:
    raw = _text((value or {}).get("kind") or (value or {}).get("type")).casefold()
    if raw in _KIND_PREFIXES:
        return _KIND_PREFIXES[raw]
    prefix = entity_id.split(":", 1)[0].casefold() if ":" in entity_id else ""
    return _KIND_PREFIXES.get(prefix, "entity")


def _target(value: Any, *, location_id: str = "", kind_hint: str = "") -> SceneLoreTarget | None:
    if isinstance(value, Mapping):
        entity_id = _text(
            value.get("entity_id")
            or value.get("npc_id")
            or value.get("creature_id")
            or value.get("monster_id")
            or value.get("actor_id")
            or value.get("location_id")
            or value.get("id")
        )
        name = _text(value.get("name") or value.get("title") or value.get("label"))
        resolved_kind = _kind(entity_id, value)
    else:
        entity_id = _text(value)
        name = ""
        resolved_kind = _kind(entity_id)
    if not entity_id or entity_id == "player" or entity_id.startswith("player:"):
        return None
    if ":" not in entity_id and kind_hint:
        entity_id = f"{kind_hint}:{_slug(entity_id)}"
    resolved_kind = kind_hint or resolved_kind
    if resolved_kind == "entity" and entity_id.startswith("npc:"):
        resolved_kind = "npc"
    return SceneLoreTarget(
        entity_id=entity_id,
        kind=resolved_kind,
        name=name or _name_from_id(entity_id),
        location_id=location_id,
    )


def _scene_containers(result: Mapping[str, Any], session: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    state = _mapping(session.get("state"))
    simulation = _mapping(session.get("simulation_state"))
    runtime = _mapping(session.get("runtime_state"))
    resolved = _mapping(result.get("resolved_result") or result.get("result"))
    return (
        _mapping(result.get("scene")),
        resolved,
        _mapping(state.get("scene")),
        _mapping(runtime.get("scene") or runtime.get("current_scene")),
        _mapping(simulation.get("scene")),
        _mapping(simulation.get("scene_population_state")),
    )


def scene_lore_targets(
    result: Mapping[str, Any],
    session: Mapping[str, Any],
    *,
    explicit_entity_ids: Sequence[str] = (),
) -> tuple[SceneLoreTarget, ...]:
    """Return current location and encountered scene entities in stable order."""

    values: dict[str, SceneLoreTarget] = {}
    location = current_location_identity(session)
    location_id = _text((location or {}).get("id"))
    if location:
        values[location_id.casefold()] = SceneLoreTarget(
            entity_id=location_id,
            kind="location",
            name=_text(location.get("name")) or _name_from_id(location_id),
        )

    def add(candidate: SceneLoreTarget | None) -> None:
        if candidate is None:
            return
        key = candidate.entity_id.casefold()
        previous = values.get(key)
        if previous is None or previous.kind == "entity":
            values[key] = candidate

    for entity_id in explicit_entity_ids:
        add(_target(entity_id, location_id=location_id))
    for container in _scene_containers(result, session):
        for key in _SCENE_ID_KEYS:
            for entity_id in container.get(key) or ():
                hint = ""
                if "npc" in key:
                    hint = "npc"
                elif "creature" in key:
                    hint = "creature"
                elif "monster" in key:
                    hint = "monster"
                add(_target(entity_id, location_id=location_id, kind_hint=hint))
        for key in _SCENE_LIST_KEYS:
            for row in container.get(key) or ():
                hint = ""
                if "npc" in key:
                    hint = "npc"
                elif "creature" in key:
                    hint = "creature"
                elif "monster" in key:
                    hint = "monster"
                add(_target(row, location_id=location_id, kind_hint=hint))
    npc = _mapping(result.get("npc"))
    add(_target(npc, location_id=location_id, kind_hint="npc") if npc else None)
    return tuple(values.values())


def _document_for_entity(documents: Sequence[Mapping[str, Any]], entity_id: str) -> bool:
    target = entity_id.casefold()
    return any(
        target
        in {
            _text(value).casefold()
            for value in (*list(row.get("entity_refs") or ()), *list(row.get("entities") or ()))
        }
        for row in documents
    )


def _rich_entity(entity: Mapping[str, Any]) -> bool:
    return bool(
        _text(entity.get("name") or entity.get("title"))
        and _text(
            entity.get("description")
            or entity.get("public_bio")
            or entity.get("sensory_profile")
            or entity.get("appearance")
            or entity.get("behavior")
        )
    )


def _context(bible: Mapping[str, Any], target: SceneLoreTarget) -> dict[str, Any]:
    visible_documents = []
    for row in _rows(bible.get("documents")):
        if _text(row.get("visibility")).casefold() not in _VISIBLE:
            continue
        summary = _text(row.get("summary_500") or row.get("summary_120") or row.get("full_text"))
        if summary:
            visible_documents.append({"title": _text(row.get("title")), "summary": summary[:600]})
        if len(visible_documents) >= 10:
            break
    entities = _mapping(bible.get("entities"))
    location = _mapping(entities.get(target.location_id)) if target.location_id else {}
    return {
        "target": target.as_dict(),
        "location": location,
        "known_world_lore": visible_documents,
    }


def _parse_json(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _stable_choices(campaign_id: str, entity_id: str) -> tuple[str, str, str, str]:
    digest = hashlib.sha256(f"{campaign_id}|{entity_id}".encode()).digest()
    names = ("Mara Venn", "Tomas Reed", "Elian Ward", "Nessa Vale", "Corin Ash", "Sera Holt")
    roles = ("innkeeper", "market steward", "local healer", "watch sergeant", "scribe", "stable master")
    traits = ("practical and observant", "warm but guarded", "direct and civic-minded", "patient and meticulous")
    histories = ("an old trade crossing", "a refuge founded after a border war", "a river settlement grown around a shrine", "a fortified market built over older ruins")
    return (
        names[digest[0] % len(names)],
        roles[digest[1] % len(roles)],
        traits[digest[2] % len(traits)],
        histories[digest[3] % len(histories)],
    )


def _fallback_location_bundle(campaign_id: str, target: SceneLoreTarget) -> dict[str, Any]:
    first_name, first_role, first_traits, history_seed = _stable_choices(campaign_id, target.entity_id)
    second_name, second_role, second_traits, _ = _stable_choices(campaign_id, target.entity_id + ":2")
    location_id = target.entity_id
    overview = (
        f"{target.name} is a lived-in settlement shaped by its roads, trades, and surrounding region. "
        "Its streets join a practical civic center, clustered homes, workshops, and public gathering places. "
        "The settlement has an established daily rhythm, recognizable local customs, and residents whose roles connect directly to travel, trade, safety, and community life."
    )
    history = (
        f"Local tradition describes {target.name} as {history_seed}. Its present institutions grew from the need to protect travelers, "
        "settle disputes, preserve supplies, and maintain links with neighboring communities. Older events remain visible in reused stonework, family names, and annual observances."
    )
    npcs = []
    for index, (name, role, traits) in enumerate(
        ((first_name, first_role, first_traits), (second_name, second_role, second_traits)),
        start=1,
    ):
        npc_id = f"npc:{_slug(target.name)}:{index}:{_slug(name)}"
        npcs.append(
            {
                "id": npc_id,
                "kind": "npc",
                "name": name,
                "role": role,
                "description": f"{name} is a {role} in {target.name}, known publicly as {traits}.",
                "personality": traits,
                "speech_style": "plainspoken and locally informed",
                "location_id": location_id,
                "visibility": "public",
                "dossier_status": "materialized",
            }
        )
    return {
        "entities": [
            {
                "id": location_id,
                "kind": "location",
                "name": target.name,
                "description": overview,
                "sensory_profile": "The sounds of work and conversation mix with weathered stone, timber, cooking smoke, and road dust.",
                "services": ["lodging", "food", "trade", "local guidance"],
                "landmarks": ["central gathering place", "market street", "local watch post"],
                "inhabitants": [row["id"] for row in npcs],
                "visibility": "public",
                "dossier_status": "materialized",
            },
            *npcs,
        ],
        "documents": [
            {"title": target.name, "topic_id": "locations", "full_text": overview, "entity_refs": [location_id]},
            {"title": f"History of {target.name}", "topic_id": "history", "full_text": history, "entity_refs": [location_id]},
        ],
        "facts": [
            {"id": f"fact:{_slug(target.name)}:settlement", "content": overview, "entity_refs": [location_id]},
            {"id": f"fact:{_slug(target.name)}:history", "content": history, "entity_refs": [location_id]},
        ],
        "relationships": [
            {"id": f"relationship:{_slug(target.name)}:{index}", "kind": "located_in", "source_id": row["id"], "target_id": location_id, "content": f"{row['name']} lives and works in {target.name}.", "entity_refs": [row["id"], location_id]}
            for index, row in enumerate(npcs, start=1)
        ],
    }


def _fallback_entity_bundle(target: SceneLoreTarget) -> dict[str, Any]:
    kind = target.kind if target.kind != "entity" else "creature"
    if kind == "npc":
        description = f"{target.name} is a person currently encountered in the campaign, with a public identity grounded in the surrounding community."
    elif kind in {"monster", "creature"}:
        description = f"{target.name} is a known {kind} of this region. Its visible anatomy, movement, habitat, and behavior define how witnesses recognize it without revealing unobserved abilities or hidden weaknesses."
    else:
        description = f"{target.name} is an established {kind} in the campaign world, described through public and presently observable facts."
    entity = {
        "id": target.entity_id,
        "kind": kind,
        "name": target.name,
        "description": description,
        "location_id": target.location_id,
        "visibility": "player_known",
        "dossier_status": "materialized",
    }
    if kind in {"monster", "creature"}:
        entity.update({"appearance": "Distinctive enough to identify at close range.", "behavior": "Acts according to its habitat, needs, and immediate circumstances.", "habitat": target.location_id})
    return {
        "entities": [entity],
        "documents": [{"title": target.name, "topic_id": f"{kind}s", "full_text": description, "entity_refs": [target.entity_id]}],
        "facts": [{"id": f"fact:{_slug(target.entity_id)}:identity", "content": description, "entity_refs": [target.entity_id]}],
        "relationships": [],
    }


def _generate_bundle(
    bible: Mapping[str, Any],
    campaign_id: str,
    target: SceneLoreTarget,
    *,
    llm_gateway: Any | None,
) -> dict[str, Any]:
    gateway = llm_gateway if llm_gateway is not None else build_app_llm_gateway()
    fallback = _fallback_location_bundle(campaign_id, target) if target.kind == "location" else _fallback_entity_bundle(target)
    if gateway is None:
        return fallback
    prompt = (
        "Return one JSON object that materializes durable, player-safe RPG canon for the target. "
        "Use existing world lore as constraints. Never contradict established facts or invent quest solutions, hidden secrets, mechanical stats, or facts the player could not know. "
        "For a location, return a rich location dossier, two to four local NPC dossiers, an overview document, a local-history document, public facts, and explicit relationships. "
        "For an NPC, creature, or monster, return one consistent dossier, one lore document, public facts, and relationships to the current location. "
        "Required top-level arrays: entities, documents, facts, relationships. Every entity needs id, kind, name, description, visibility. Every document needs title, topic_id, full_text, entity_refs. Return JSON only."
    )
    try:
        raw = gateway.generate(
            prompt,
            context=_context(bible, target),
            timeout_s=30.0,
            provider_options={
                "temperature": 0.35,
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object"},
            },
        )
        parsed = _parse_json(raw)
        if all(isinstance(parsed.get(key), list) for key in ("entities", "documents", "facts", "relationships")):
            return parsed
    except Exception:
        pass
    return fallback


def _merge_bundle(
    bible: dict[str, Any],
    bundle: Mapping[str, Any],
    *,
    revision: int,
    source_target: SceneLoreTarget,
) -> tuple[list[str], list[str]]:
    entities = deepcopy(_mapping(bible.get("entities")))
    documents = _rows(bible.get("documents"))
    facts = _rows(bible.get("facts"))
    relationships = _rows(bible.get("relationships"))
    discovery = deepcopy(_mapping(bible.get("discovery_state")))
    page_status = deepcopy(_mapping(discovery.get("pages")))
    entity_status = deepcopy(_mapping(discovery.get("entities")))
    created_entities: list[str] = []
    created_documents: list[str] = []

    for index, raw in enumerate(bundle.get("entities") or (), start=1):
        if not isinstance(raw, Mapping):
            continue
        row = deepcopy(dict(raw))
        entity_id = _text(row.get("id") or row.get("entity_id"))
        if not entity_id:
            entity_id = f"{_text(row.get('kind')) or 'entity'}:{_slug(_text(row.get('name')) or str(index))}"
        row["id"] = entity_id
        row.setdefault("kind", _kind(entity_id, row))
        row.setdefault("name", _name_from_id(entity_id))
        row.setdefault("visibility", "public")
        row["canon_revision"] = revision
        row["provenance"] = {**_mapping(row.get("provenance")), "source": "runtime_scene_materialization_v1", "source_target_id": source_target.entity_id}
        existing = deepcopy(_mapping(entities.get(entity_id)))
        if not _rich_entity(existing):
            entities[entity_id] = {**row, **{key: value for key, value in existing.items() if value not in (None, "", [], {})}}
            created_entities.append(entity_id)
        entity_status.setdefault(entity_id, "partially_known")

    occupied_documents = {_text(row.get("document_id")) for row in documents}
    for index, raw in enumerate(bundle.get("documents") or (), start=1):
        if not isinstance(raw, Mapping):
            continue
        row = deepcopy(dict(raw))
        refs = [_text(value) for value in row.get("entity_refs") or () if _text(value)]
        if refs and any(_document_for_entity(documents, entity_id) for entity_id in refs):
            continue
        title = _text(row.get("title")) or source_target.name
        document_id = _text(row.get("document_id")) or f"lore:{_text(row.get('topic_id')) or source_target.kind}:{_slug(title)}"
        if document_id in occupied_documents:
            document_id = f"{document_id}:{index}"
        full_text = _text(row.get("full_text") or row.get("content") or row.get("summary"))
        if not full_text:
            continue
        row.update(
            {
                "document_id": document_id,
                "topic_id": _text(row.get("topic_id")) or f"{source_target.kind}s",
                "title": title,
                "full_text": full_text,
                "summary_500": _text(row.get("summary_500")) or full_text[:500].rstrip(),
                "summary_120": _text(row.get("summary_120")) or full_text[:120].rstrip(),
                "keywords": list(dict.fromkeys([*list(row.get("keywords") or ()), *refs, title])),
                "entity_refs": refs or [source_target.entity_id],
                "visibility": _text(row.get("visibility")) or "public",
                "canon_revision": revision,
                "provenance": {**_mapping(row.get("provenance")), "source": "runtime_scene_materialization_v1", "source_target_id": source_target.entity_id},
            }
        )
        documents.append(row)
        occupied_documents.add(document_id)
        page_status[document_id] = "partially_known"
        created_documents.append(document_id)

    fact_ids = {_text(row.get("id") or row.get("evidence_id")) for row in facts}
    for index, raw in enumerate(bundle.get("facts") or (), start=1):
        if not isinstance(raw, Mapping):
            continue
        row = deepcopy(dict(raw))
        fact_id = _text(row.get("id") or row.get("evidence_id")) or f"fact:{_slug(source_target.entity_id)}:{index}"
        if fact_id in fact_ids:
            continue
        content = _text(row.get("content") or row.get("statement"))
        if not content:
            continue
        row.update({"id": fact_id, "content": content, "authority": "objective_canon", "approved_authority": "objective_canon", "visibility": _text(row.get("visibility")) or "public", "canon_revision": revision})
        facts.append(row)
        fact_ids.add(fact_id)

    relationship_ids = {_text(row.get("id")) for row in relationships}
    for index, raw in enumerate(bundle.get("relationships") or (), start=1):
        if not isinstance(raw, Mapping):
            continue
        row = deepcopy(dict(raw))
        relationship_id = _text(row.get("id")) or f"relationship:{_slug(source_target.entity_id)}:{index}"
        if relationship_id in relationship_ids:
            continue
        row.update({"id": relationship_id, "authority": "objective_canon", "approved_authority": "objective_canon", "visibility": _text(row.get("visibility")) or "public", "canon_revision": revision})
        relationships.append(row)
        relationship_ids.add(relationship_id)

    bible["entities"] = entities
    bible["documents"] = documents
    bible["facts"] = facts
    bible["relationships"] = relationships
    discovery["pages"] = page_status
    discovery["entities"] = entity_status
    discovery.setdefault("discoveries", [])
    bible["discovery_state"] = discovery
    return created_entities, created_documents


def materialize_scene_lore(
    bible: Mapping[str, Any],
    session: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    campaign_id: str,
    explicit_entity_ids: Sequence[str] = (),
    canon_revision: int | None = None,
    llm_gateway: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate and merge missing current-scene canon once, with deterministic fallback."""

    candidate = deepcopy(dict(bible))
    candidate.setdefault("documents", [])
    candidate.setdefault("entities", {})
    candidate.setdefault("facts", [])
    candidate.setdefault("relationships", [])
    revision = int(canon_revision or int(candidate.get("canon_revision") or 0) + 1)
    created_entities: list[str] = []
    created_documents: list[str] = []
    targets = scene_lore_targets(result, session, explicit_entity_ids=explicit_entity_ids)
    for target in targets:
        existing = _mapping(_mapping(candidate.get("entities")).get(target.entity_id))
        has_document = _document_for_entity(_rows(candidate.get("documents")), target.entity_id)
        if _rich_entity(existing) and has_document:
            continue
        bundle = _generate_bundle(candidate, campaign_id, target, llm_gateway=llm_gateway)
        entity_ids, document_ids = _merge_bundle(candidate, bundle, revision=revision, source_target=target)
        created_entities.extend(entity_ids)
        created_documents.extend(document_ids)
    changed = bool(created_entities or created_documents)
    if changed:
        candidate["canon_revision"] = revision
        manifest = deepcopy(_mapping(candidate.get("manifest")))
        manifest.update({
            "document_count": len(_rows(candidate.get("documents"))),
            "entity_count": len(_mapping(candidate.get("entities"))),
            "fact_count": len(_rows(candidate.get("facts"))),
            "relationship_count": len(_rows(candidate.get("relationships"))),
        })
        candidate["manifest"] = manifest
    return candidate, {
        "changed": changed,
        "targets": [target.as_dict() for target in targets],
        "created_entity_ids": list(dict.fromkeys(created_entities)),
        "created_document_ids": list(dict.fromkeys(created_documents)),
        "canon_revision": revision if changed else int(candidate.get("canon_revision") or 0),
        "generator": "llm_with_deterministic_fallback",
    }
