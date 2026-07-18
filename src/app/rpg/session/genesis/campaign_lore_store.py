"""PostgreSQL-backed Campaign Bible access and on-demand location lore."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from app.persistence.database import default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.rpg_campaign_bible_repository import campaign_bible_hash
from app.persistence.unit_of_work import unit_of_work
from app.rpg.llm_app_gateway import build_app_llm_gateway
from app.rpg.session.service import save_session

_PLAYER_VISIBLE_VISIBILITY = {
    "public",
    "player_known",
    "learned",
    "partially_known",
    "disputed",
}
_PROJECTION_KEYS = (
    "documents",
    "entities",
    "facts",
    "retrieval_cards",
    "relationships",
    "knowledge_rules",
    "story_threads",
    "indexes",
    "discovery_state",
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or () if isinstance(row, Mapping)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "unknown-location"


def _campaign_id(session_id: str, session: Mapping[str, Any]) -> str:
    manifest = _mapping(session.get("manifest"))
    return _text(session_id or manifest.get("session_id") or manifest.get("id"))


def _campaign_title(session: Mapping[str, Any], campaign_id: str) -> str:
    state = _mapping(session.get("state"))
    metadata = _mapping(state.get("metadata"))
    manifest = _mapping(session.get("manifest"))
    return _text(
        state.get("title")
        or metadata.get("campaign_name")
        or metadata.get("title")
        or manifest.get("title")
        or manifest.get("name")
        or campaign_id
    )


def _location_from_value(value: Any) -> tuple[str, str] | None:
    if isinstance(value, Mapping):
        location_id = _text(
            value.get("id")
            or value.get("location_id")
            or value.get("node_id")
            or value.get("area_id")
        )
        name = _text(
            value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("location_name")
        )
        if location_id or name:
            return location_id, name
        return None
    text = _text(value)
    if not text:
        return None
    if text.casefold().startswith("location:"):
        return text, ""
    return "", text


def current_location_identity(session: Mapping[str, Any]) -> dict[str, str] | None:
    """Resolve the current location across legacy and current session shapes."""

    state = _mapping(session.get("state"))
    player = _mapping(state.get("player"))
    world = _mapping(state.get("world"))
    simulation = _mapping(session.get("simulation_state"))
    runtime = _mapping(session.get("runtime_state"))
    map_state = _mapping(state.get("map") or session.get("map_state"))

    explicit_id = _text(
        state.get("current_location_id")
        or player.get("current_location_id")
        or world.get("current_location_id")
        or simulation.get("current_location_id")
        or runtime.get("current_location_id")
        or map_state.get("current_location_id")
    )
    explicit_name = _text(
        state.get("current_location_name")
        or player.get("current_location_name")
        or world.get("current_location_name")
        or simulation.get("current_location_name")
        or runtime.get("current_location_name")
    )

    location_id = explicit_id
    name = explicit_name
    candidates = (
        state.get("current_location"),
        state.get("location"),
        player.get("current_location"),
        player.get("location"),
        world.get("current_location"),
        world.get("location"),
        simulation.get("current_location"),
        simulation.get("location"),
        runtime.get("current_location"),
        map_state.get("current_location"),
    )
    for candidate in candidates:
        resolved = _location_from_value(candidate)
        if resolved is None:
            continue
        candidate_id, candidate_name = resolved
        location_id = location_id or candidate_id
        name = name or candidate_name
        if location_id and name:
            break

    if not location_id and not name:
        return None
    if not name:
        name = location_id.split(":", 1)[-1].replace("_", " ").replace("-", " ").title()
    if not location_id:
        location_id = f"location:{_slug(name)}"
    elif not location_id.casefold().startswith("location:"):
        location_id = f"location:{_slug(location_id)}"
    return {"id": location_id, "name": name}


def _portable_bible(session: Mapping[str, Any]) -> dict[str, Any]:
    projection = deepcopy(_mapping(session.get("campaign_bible_projection")))
    state = _mapping(session.get("state"))
    state_bible = _mapping(state.get("campaign_bible"))
    manifest = _mapping(session.get("manifest"))

    documents = _rows(projection.get("documents"))
    if not documents:
        documents = _rows(_mapping(state_bible.get("lore_pages")).values())
    entities = deepcopy(_mapping(projection.get("entities")))
    if not entities:
        for key, kind in (
            ("npc_dossiers", "npc"),
            ("location_dossiers", "location"),
            ("faction_dossiers", "faction"),
        ):
            for entity_id, row in _mapping(state.get(key)).items():
                if isinstance(row, Mapping):
                    entities[str(entity_id)] = {"kind": kind, **dict(row)}

    discovery = deepcopy(
        _mapping(projection.get("discovery_state"))
        or _mapping(state_bible.get("discovery_state"))
    )
    discovery.setdefault("pages", {})
    discovery.setdefault("entities", {})
    discovery.setdefault("discoveries", [])

    bible: dict[str, Any] = {
        "schema_version": _text(
            projection.get("schema_version")
            or state_bible.get("schema_version")
            or manifest.get("schema_version")
            or "campaign-bible-v1"
        ),
        "canon_revision": int(
            projection.get("canon_revision")
            or state_bible.get("canon_revision")
            or 0
        ),
        "manifest": deepcopy(_mapping(projection.get("manifest") or state_bible.get("manifest"))),
        "documents": documents,
        "entities": entities,
        "discovery_state": discovery,
    }
    for key in _PROJECTION_KEYS:
        if key in {"documents", "entities", "discovery_state"}:
            continue
        value = projection.get(key)
        if value is not None:
            bible[key] = deepcopy(value)
        elif key not in bible:
            bible[key] = [] if key != "indexes" else {}
    return bible


def _document_matches_location(document: Mapping[str, Any], location: Mapping[str, str]) -> bool:
    document_id = _text(document.get("document_id")).casefold()
    title = _text(document.get("title")).casefold()
    location_id = _text(location.get("id")).casefold()
    location_name = _text(location.get("name")).casefold()
    refs = {_text(value).casefold() for value in document.get("entity_refs") or ()}
    keywords = {_text(value).casefold() for value in document.get("keywords") or ()}
    return bool(
        document_id == f"lore:location:{_slug(location_name)}"
        or location_id in refs
        or location_id in keywords
        or (
            _text(document.get("topic_id")).casefold() in {"location", "locations"}
            and title == location_name
        )
    )


def _public_world_context(bible: Mapping[str, Any]) -> list[str]:
    context: list[str] = []
    for document in _rows(bible.get("documents")):
        if _text(document.get("visibility")) not in _PLAYER_VISIBLE_VISIBILITY:
            continue
        summary = _text(document.get("summary_500") or document.get("summary_120"))
        if summary:
            context.append(summary)
        if len(context) >= 12:
            break
    return context


def _fallback_location_text(name: str) -> str:
    lowered = name.casefold()
    if "tavern" in lowered or "inn" in lowered:
        return (
            f"{name} is a well-used gathering place where travelers, workers, and local regulars exchange news over food and drink. "
            "Its common room bears the practical marks of constant traffic: smoke-darkened beams, repaired furniture, a working hearth, and corners claimed by familiar patrons. "
            "The establishment serves as both shelter and information crossroads, so changes in the surrounding community are often heard here before they become public knowledge elsewhere."
        )
    return (
        f"{name} is a known location within the campaign's lived-in world, shaped by the people who use it and the routes that connect it to nearby settlements. "
        "Its visible layout, materials, sounds, and daily activity reflect the wider region without revealing hidden threats or undiscovered secrets. "
        "The place can support travel, conversation, investigation, trade, or conflict as the campaign develops."
    )


def _generate_location_text(
    bible: Mapping[str, Any],
    session: Mapping[str, Any],
    location: Mapping[str, str],
    *,
    llm_gateway: Any | None = None,
) -> str:
    gateway = llm_gateway or build_app_llm_gateway()
    if gateway is not None:
        state = _mapping(session.get("state"))
        metadata = _mapping(state.get("metadata"))
        prompt = (
            "Write a player-safe Campaign Bible entry for the current RPG location. "
            "Use 110 to 190 words in three short paragraphs. Describe the place's visible layout, atmosphere, ordinary occupants, local function, and relationship to the surrounding world. "
            "Ground the entry in the supplied campaign context. Do not invent hidden secrets, quest solutions, unique magical powers, undiscovered enemies, or game mechanics. Return prose only."
        )
        try:
            generated = _text(
                gateway.generate(
                    prompt,
                    context={
                        "location": dict(location),
                        "campaign": {
                            "title": _campaign_title(session, "campaign"),
                            "genre": _text(metadata.get("genre") or metadata.get("campaign_template")),
                            "tone": _text(metadata.get("tone")),
                        },
                        "known_world_lore": _public_world_context(bible),
                    },
                    timeout_s=20.0,
                )
            )
            if generated:
                return generated
        except Exception:
            pass
    return _fallback_location_text(_text(location.get("name")) or "Current Location")


def ensure_current_location_document(
    bible: Mapping[str, Any],
    session: Mapping[str, Any],
    *,
    canon_revision: int | None = None,
    llm_gateway: Any | None = None,
) -> tuple[dict[str, Any], str | None, bool]:
    """Add a public location page when the current location lacks one."""

    location = current_location_identity(session)
    candidate = deepcopy(dict(bible))
    documents = _rows(candidate.get("documents"))
    candidate["documents"] = documents
    if location is None:
        return candidate, None, False
    for document in documents:
        if _document_matches_location(document, location):
            return candidate, _text(document.get("document_id")) or None, False

    full_text = _generate_location_text(
        candidate,
        session,
        location,
        llm_gateway=llm_gateway,
    )
    revision = int(
        canon_revision
        if canon_revision is not None
        else int(candidate.get("canon_revision") or 0) + 1
    )
    document_id = f"lore:location:{_slug(location['name'])}"
    summary_500 = full_text[:500].rstrip()
    summary_120 = full_text[:120].rstrip()
    document = {
        "document_id": document_id,
        "topic_id": "locations",
        "title": location["name"],
        "full_text": full_text,
        "summary_500": summary_500,
        "summary_120": summary_120,
        "keywords": [location["id"], location["name"], "current location"],
        "entity_refs": [location["id"]],
        "visibility": "public",
        "canon_revision": revision,
        "provenance": {
            "source": "on_demand_current_location_lore",
            "generator": "llm_with_deterministic_fallback",
        },
    }
    documents.append(document)

    entities = deepcopy(_mapping(candidate.get("entities")))
    entity = deepcopy(_mapping(entities.get(location["id"])))
    entity.update(
        {
            "kind": "location",
            "name": location["name"],
            "visibility": _text(entity.get("visibility")) or "public",
            "description": _text(entity.get("description")) or summary_500,
        }
    )
    entities[location["id"]] = entity
    candidate["entities"] = entities

    discovery = deepcopy(_mapping(candidate.get("discovery_state")))
    pages = deepcopy(_mapping(discovery.get("pages")))
    entity_statuses = deepcopy(_mapping(discovery.get("entities")))
    pages[document_id] = "public_at_campaign_start"
    entity_statuses[location["id"]] = "public_at_campaign_start"
    discovery["pages"] = pages
    discovery["entities"] = entity_statuses
    discovery.setdefault("discoveries", [])
    candidate["discovery_state"] = discovery
    candidate["canon_revision"] = revision
    return candidate, document_id, True


def _hydrate_session(
    session: Mapping[str, Any],
    bible: Mapping[str, Any],
    *,
    revision: int,
    content_hash: str,
) -> dict[str, Any]:
    hydrated = deepcopy(dict(session))
    projection = {
        key: deepcopy(bible.get(key, [] if key != "indexes" else {}))
        for key in _PROJECTION_KEYS
    }
    projection.update(
        {
            "schema_version": bible.get("schema_version"),
            "manifest": deepcopy(_mapping(bible.get("manifest"))),
            "content_hash": content_hash,
            "canon_revision": revision,
        }
    )
    hydrated["campaign_bible_projection"] = projection

    state = _mapping(hydrated.get("state"))
    state_bible = _mapping(state.get("campaign_bible"))
    documents = _rows(bible.get("documents"))
    state_bible.update(
        {
            "schema_version": bible.get("schema_version"),
            "canon_revision": revision,
            "content_hash": content_hash,
            "manifest": deepcopy(_mapping(bible.get("manifest"))),
            "discovery_state": deepcopy(_mapping(bible.get("discovery_state"))),
            "lore_pages": {
                _text(row.get("document_id")): deepcopy(row)
                for row in documents
                if _text(row.get("document_id"))
                and _text(row.get("visibility")) in _PLAYER_VISIBLE_VISIBILITY
            },
        }
    )
    state["campaign_bible"] = state_bible

    entities = _mapping(bible.get("entities"))
    state["npc_dossiers"] = {
        entity_id: deepcopy(row)
        for entity_id, row in entities.items()
        if isinstance(row, Mapping) and _text(row.get("kind")) == "npc"
    }
    state["location_dossiers"] = {
        entity_id: deepcopy(row)
        for entity_id, row in entities.items()
        if isinstance(row, Mapping) and _text(row.get("kind")) == "location"
    }
    state["faction_dossiers"] = {
        entity_id: deepcopy(row)
        for entity_id, row in entities.items()
        if isinstance(row, Mapping) and _text(row.get("kind")) == "faction"
    }
    hydrated["state"] = state

    runtime = _mapping(hydrated.get("runtime_state"))
    runtime["campaign_bible_revision"] = revision
    runtime["campaign_bible_content_hash"] = content_hash
    hydrated["runtime_state"] = runtime
    manifest = _mapping(hydrated.get("manifest"))
    manifest["campaign_bible_revision"] = revision
    manifest["campaign_bible_content_hash"] = content_hash
    hydrated["manifest"] = manifest
    return hydrated


def _save_portable_projection(session: dict[str, Any]) -> dict[str, Any]:
    try:
        return save_session(session, compact=True)
    except Exception:
        return session


def load_campaign_lore(
    session_id: str,
    session: Mapping[str, Any],
    *,
    ensure_current_location: bool = True,
    database: Any | None = None,
    llm_gateway: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load authoritative lore from PostgreSQL and generate missing current-location lore."""

    campaign_id = _campaign_id(session_id, session)
    portable = _portable_bible(session)
    location = current_location_identity(session)
    try:
        db = database or default_database()
        context = bootstrap_local_tenant(db)
        with unit_of_work(db) as work:
            campaign = work.rpg.get_campaign(context, campaign_id, for_update=True)
            if campaign is None:
                manifest = _mapping(session.get("manifest"))
                setup = _mapping(session.get("setup_payload"))
                work.rpg.create_campaign(
                    context,
                    campaign_id=campaign_id,
                    title=_campaign_title(session, campaign_id),
                    state=deepcopy(_mapping(session.get("state"))),
                    engine_version="rpg-campaign-lore-v1",
                    schema_version=_text(manifest.get("schema_version")) or "rpg-session-v1",
                    seed=_text(manifest.get("seed") or setup.get("seed")) or "0",
                    metadata={"source": "campaign_lore_api", "portable_backfill": True},
                )
            stored = work.campaign_bibles.get(context, campaign_id, for_update=True)
            bible = deepcopy(stored["document"] if stored is not None else portable)
            generated_document_id: str | None = None
            generated = False
            if ensure_current_location:
                bible, generated_document_id, generated = ensure_current_location_document(
                    bible,
                    session,
                    canon_revision=(int(stored["revision"]) + 1 if stored is not None else 1),
                    llm_gateway=llm_gateway,
                )
            should_write = stored is None or campaign_bible_hash(bible) != str(stored["content_hash"])
            if should_write:
                next_revision = int(stored["revision"]) + 1 if stored is not None else 1
                bible["canon_revision"] = max(int(bible.get("canon_revision") or 0), next_revision)
                stored = work.campaign_bibles.put(
                    context,
                    campaign_id=campaign_id,
                    document=bible,
                    expected_revision=(int(stored["revision"]) if stored is not None else 0),
                    provenance={
                        **(_mapping(stored.get("provenance")) if stored is not None else {}),
                        "last_source": "campaign_lore_api",
                        "generated_current_location": generated,
                        "current_location_id": location.get("id") if location else None,
                    },
                    consistency_report=(
                        _mapping(stored.get("consistency_report")) if stored is not None else {}
                    ),
                    completeness=(
                        _mapping(stored.get("completeness")) if stored is not None else {}
                    ),
                )
            work.commit()

        assert stored is not None
        hydrated = _hydrate_session(
            session,
            stored["document"],
            revision=int(stored["revision"]),
            content_hash=str(stored["content_hash"]),
        )
        existing_hash = _text(
            _mapping(session.get("campaign_bible_projection")).get("content_hash")
        )
        if generated or existing_hash != str(stored["content_hash"]):
            hydrated = _save_portable_projection(hydrated)
        return hydrated, {
            "mode": "postgresql_authority",
            "persisted": True,
            "campaign_id": campaign_id,
            "revision": int(stored["revision"]),
            "content_hash": str(stored["content_hash"]),
            "current_location": location,
            "generated_current_location": generated,
            "generated_document_id": generated_document_id,
        }
    except Exception as exc:
        generated_document_id: str | None = None
        generated = False
        bible = portable
        if ensure_current_location:
            bible, generated_document_id, generated = ensure_current_location_document(
                bible,
                session,
                llm_gateway=llm_gateway,
            )
        digest = campaign_bible_hash(bible)
        fallback = _hydrate_session(
            session,
            bible,
            revision=int(bible.get("canon_revision") or 0),
            content_hash=digest,
        )
        if generated:
            fallback = _save_portable_projection(fallback)
        return fallback, {
            "mode": "portable_projection_fallback",
            "persisted": False,
            "campaign_id": campaign_id,
            "content_hash": digest,
            "current_location": location,
            "generated_current_location": generated,
            "generated_document_id": generated_document_id,
            "error": type(exc).__name__,
        }


def persist_campaign_lore(
    session_id: str,
    session: Mapping[str, Any],
    *,
    database: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persist a changed lore projection, including discovery state, to PostgreSQL."""

    campaign_id = _campaign_id(session_id, session)
    portable = _portable_bible(session)
    try:
        db = database or default_database()
        context = bootstrap_local_tenant(db)
        with unit_of_work(db) as work:
            campaign = work.rpg.get_campaign(context, campaign_id, for_update=True)
            if campaign is None:
                manifest = _mapping(session.get("manifest"))
                work.rpg.create_campaign(
                    context,
                    campaign_id=campaign_id,
                    title=_campaign_title(session, campaign_id),
                    state=deepcopy(_mapping(session.get("state"))),
                    engine_version="rpg-campaign-lore-v1",
                    schema_version=_text(manifest.get("schema_version")) or "rpg-session-v1",
                    seed=_text(manifest.get("seed")) or "0",
                    metadata={"source": "campaign_lore_discovery"},
                )
            current = work.campaign_bibles.get(context, campaign_id, for_update=True)
            bible = deepcopy(current["document"] if current is not None else portable)
            for key in _PROJECTION_KEYS:
                if key in portable:
                    bible[key] = deepcopy(portable[key])
            next_revision = int(current["revision"]) + 1 if current is not None else 1
            bible["canon_revision"] = max(int(bible.get("canon_revision") or 0), next_revision)
            stored = work.campaign_bibles.put(
                context,
                campaign_id=campaign_id,
                document=bible,
                expected_revision=(int(current["revision"]) if current is not None else 0),
                provenance={
                    **(_mapping(current.get("provenance")) if current is not None else {}),
                    "last_source": "campaign_lore_discovery",
                },
                consistency_report=(
                    _mapping(current.get("consistency_report")) if current is not None else {}
                ),
                completeness=(
                    _mapping(current.get("completeness")) if current is not None else {}
                ),
            )
            work.commit()
        hydrated = _hydrate_session(
            session,
            stored["document"],
            revision=int(stored["revision"]),
            content_hash=str(stored["content_hash"]),
        )
        hydrated = _save_portable_projection(hydrated)
        return hydrated, {
            "mode": "postgresql_authority",
            "persisted": True,
            "campaign_id": campaign_id,
            "revision": int(stored["revision"]),
            "content_hash": str(stored["content_hash"]),
        }
    except Exception as exc:
        fallback = _save_portable_projection(dict(session))
        return fallback, {
            "mode": "portable_projection_fallback",
            "persisted": False,
            "campaign_id": campaign_id,
            "error": type(exc).__name__,
        }
