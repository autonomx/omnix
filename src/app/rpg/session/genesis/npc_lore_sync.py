"""Synchronize encountered NPC biographies into PostgreSQL Campaign Bible canon."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping, Sequence

from app.persistence.database import default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.rpg_campaign_bible_repository import campaign_bible_hash
from app.persistence.unit_of_work import unit_of_work
from app.rpg.profiles.dynamic_npc_profiles import load_npc_profile
from app.rpg.world.npc_biography_registry import get_npc_biography

from .campaign_lore_store import (
    _campaign_id,
    _campaign_title,
    _hydrate_session,
    _mapping,
    _portable_bible,
    _save_portable_projection,
    _text,
    current_location_identity,
)

_PLAYER_VISIBLE_VISIBILITY = {
    "public",
    "player_known",
    "learned",
    "partially_known",
    "disputed",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "unknown-npc"


def _npc_id(value: Any) -> str:
    text = _text(value)
    if not text or text == "player":
        return ""
    return text if text.casefold().startswith("npc:") else f"npc:{text}"


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or () if isinstance(row, Mapping)]


def _values(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return [_text(item) for item in value if _text(item)]


def _current_tick(session: Mapping[str, Any]) -> int:
    state = _mapping(session.get("state"))
    simulation = _mapping(session.get("simulation_state"))
    runtime = _mapping(session.get("runtime_state"))
    for value in (
        simulation.get("tick"),
        simulation.get("turn"),
        runtime.get("tick"),
        runtime.get("turn"),
        state.get("tick"),
        state.get("turn"),
    ):
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _profile_containers(session: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    state = _mapping(session.get("state"))
    simulation = _mapping(session.get("simulation_state"))
    runtime = _mapping(session.get("runtime_state"))
    return (
        _mapping(state.get("npc_dossiers")),
        _mapping(simulation.get("npc_index")),
        _mapping(simulation.get("npcs")),
        _mapping(runtime.get("npc_index")),
        _mapping(_mapping(simulation.get("social_state")).get("profiles")),
        _mapping(_mapping(runtime.get("social_state")).get("profiles")),
    )


def _lookup_session_profile(session: Mapping[str, Any], npc_id: str) -> dict[str, Any]:
    normalized = npc_id.casefold()
    for container in _profile_containers(session):
        for key, value in container.items():
            if not isinstance(value, Mapping):
                continue
            row = {"npc_id": str(key), **dict(value)}
            aliases = {
                _npc_id(key).casefold(),
                _npc_id(row.get("npc_id") or row.get("id")).casefold(),
                _npc_id(row.get("name")).casefold(),
            }
            if normalized in aliases:
                return row
    return {}


def _add_present_id(output: list[str], value: Any) -> None:
    npc_id = _npc_id(value)
    if npc_id and npc_id.casefold() not in {item.casefold() for item in output}:
        output.append(npc_id)


def encountered_npc_ids(
    session: Mapping[str, Any],
    *,
    explicit_npc_ids: Sequence[str] = (),
) -> tuple[str, ...]:
    """Return stable NPC IDs that are present, nearby, or speaking this turn."""

    output: list[str] = []
    for value in explicit_npc_ids:
        _add_present_id(output, value)

    state = _mapping(session.get("state"))
    simulation = _mapping(session.get("simulation_state"))
    runtime = _mapping(session.get("runtime_state"))
    location = current_location_identity(session) or {}
    location_id = _text(location.get("id"))

    scene_population = _mapping(simulation.get("scene_population_state"))
    for row in scene_population.get("present_npcs") or ():
        if isinstance(row, Mapping):
            _add_present_id(output, row.get("npc_id") or row.get("id"))
        else:
            _add_present_id(output, row)

    present_state = _mapping(simulation.get("present_npc_state"))
    for value in present_state.get(location_id) or ():
        _add_present_id(output, value)
    for row in _mapping(present_state.get("by_location")).values():
        for npc in _mapping(row).get("present_npcs") or ():
            if isinstance(npc, Mapping):
                _add_present_id(output, npc.get("npc_id") or npc.get("id"))
            else:
                _add_present_id(output, npc)

    scenes = (
        _mapping(state.get("scene")),
        _mapping(runtime.get("current_scene")),
        _mapping(runtime.get("scene")),
        _mapping(simulation.get("scene")),
    )
    for scene in scenes:
        for key in ("present_npc_ids", "nearby_npc_ids", "actor_ids"):
            for value in scene.get(key) or ():
                _add_present_id(output, value)
        for key in ("present_npcs", "nearby_npcs", "npcs"):
            for row in scene.get(key) or ():
                if isinstance(row, Mapping):
                    _add_present_id(output, row.get("npc_id") or row.get("id"))
                else:
                    _add_present_id(output, row)

    player = _mapping(simulation.get("player_state"))
    for value in player.get("nearby_npc_ids") or ():
        _add_present_id(output, value)
    return tuple(output)


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _profile_biography(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(profile.get("biography"))


def _profile_personality(profile: Mapping[str, Any]) -> Mapping[str, Any]:
    value = profile.get("personality")
    return _mapping(value) if isinstance(value, Mapping) else {}


def _personality_text(*profiles: Mapping[str, Any]) -> str:
    for profile in profiles:
        value = profile.get("personality")
        if isinstance(value, str) and _text(value):
            return _text(value)
        mapping = _profile_personality(profile)
        traits = _values(mapping.get("traits")) or _values(profile.get("personality_traits"))
        temperament = _text(mapping.get("temperament"))
        parts = [part for part in (temperament, ", ".join(traits)) if part]
        if parts:
            return "; ".join(parts)
    return ""


def _speech_style(*profiles: Mapping[str, Any]) -> str:
    for profile in profiles:
        value = profile.get("speech_style") or profile.get("speaking_style")
        if isinstance(value, str) and _text(value):
            return _text(value)
        if isinstance(value, Mapping):
            tone = _text(value.get("tone"))
            quirks = _values(value.get("quirks"))
            parts = [part for part in (tone, ", ".join(quirks)) if part]
            if parts:
                return "; ".join(parts)
        personality = _profile_personality(profile)
        if _text(personality.get("speech_style")):
            return _text(personality.get("speech_style"))
    return ""


def _public_bio(
    *,
    name: str,
    role: str,
    location_name: str,
    existing: Mapping[str, Any],
    session_profile: Mapping[str, Any],
    dynamic_profile: Mapping[str, Any],
    registry_profile: Mapping[str, Any],
) -> str:
    for profile in (existing, session_profile, dynamic_profile, registry_profile):
        biography = _profile_biography(profile)
        text = _first_text(
            profile.get("public_bio"),
            biography.get("short_summary"),
            biography.get("public_reputation"),
            profile.get("short_bio"),
            profile.get("description"),
        )
        if text and "no detailed biography has been registered yet" not in text.casefold():
            return text
    role_text = role or "person encountered during the campaign"
    location_text = f" at {location_name}" if location_name else ""
    personality = _personality_text(existing, session_profile, dynamic_profile, registry_profile)
    manner = f" Their visible manner is {personality}." if personality else ""
    return f"{name} is a {role_text} first encountered{location_text}.{manner}".strip()


def _document_matches_npc(document: Mapping[str, Any], entity_id: str, name: str) -> bool:
    if _text(document.get("visibility")) not in _PLAYER_VISIBLE_VISIBILITY:
        return False
    refs = {
        _text(value).casefold()
        for value in (
            list(document.get("entity_refs") or ())
            + list(document.get("entities") or ())
        )
        if _text(value)
    }
    return bool(
        entity_id.casefold() in refs
        or (
            _text(document.get("topic_id")).casefold() in {"npc", "npcs", "characters"}
            and _text(document.get("title")).casefold() == name.casefold()
        )
    )


def ensure_encountered_npc_lore(
    bible: Mapping[str, Any],
    session: Mapping[str, Any],
    *,
    explicit_npc_ids: Sequence[str] = (),
    canon_revision: int | None = None,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...], bool]:
    """Add a player-known Campaign Bible biography for every encountered NPC."""

    candidate = deepcopy(dict(bible))
    entities = deepcopy(_mapping(candidate.get("entities")))
    documents = _rows(candidate.get("documents"))
    discovery = deepcopy(_mapping(candidate.get("discovery_state")))
    page_statuses = deepcopy(_mapping(discovery.get("pages")))
    entity_statuses = deepcopy(_mapping(discovery.get("entities")))
    discovery.setdefault("discoveries", [])
    location = current_location_identity(session) or {}
    location_id = _text(location.get("id"))
    location_name = _text(location.get("name"))
    revision = int(
        canon_revision
        if canon_revision is not None
        else int(candidate.get("canon_revision") or 0) + 1
    )
    ensured: list[str] = []
    created: list[str] = []
    changed = False

    for runtime_npc_id in encountered_npc_ids(
        session,
        explicit_npc_ids=explicit_npc_ids,
    ):
        entity_id = next(
            (
                key
                for key in entities
                if str(key).casefold() == runtime_npc_id.casefold()
            ),
            runtime_npc_id,
        )
        existing = deepcopy(_mapping(entities.get(entity_id)))
        session_profile = _lookup_session_profile(session, runtime_npc_id)
        dynamic_profile = _mapping(load_npc_profile(runtime_npc_id))
        registry_profile = _mapping(get_npc_biography(runtime_npc_id.split(":", 1)[-1]))
        name = _first_text(
            existing.get("name"),
            session_profile.get("name"),
            dynamic_profile.get("name"),
            registry_profile.get("name"),
            runtime_npc_id.split(":", 1)[-1].replace("_", " ").title(),
        )
        role = _first_text(
            existing.get("role"),
            session_profile.get("role"),
            _mapping(dynamic_profile.get("evolution")).get("current_role"),
            registry_profile.get("role"),
            "Local NPC",
        )
        public_bio = _public_bio(
            name=name,
            role=role,
            location_name=location_name,
            existing=existing,
            session_profile=session_profile,
            dynamic_profile=dynamic_profile,
            registry_profile=registry_profile,
        )
        appearance = _first_text(
            existing.get("appearance"),
            session_profile.get("appearance"),
            dynamic_profile.get("appearance"),
            registry_profile.get("appearance"),
        )
        personality = _personality_text(
            existing,
            session_profile,
            dynamic_profile,
            registry_profile,
        )
        speech_style = _speech_style(
            existing,
            session_profile,
            dynamic_profile,
            registry_profile,
        )
        aliases = list(
            dict.fromkeys(
                [
                    *(_values(existing.get("entity_refs"))),
                    entity_id,
                    runtime_npc_id,
                    _text(registry_profile.get("npc_id")),
                ]
            )
        )
        aliases = [value for value in aliases if value]
        biography = deepcopy(_mapping(existing.get("biography")))
        biography.setdefault("short_summary", public_bio)
        biography.setdefault("public_reputation", public_bio)
        updated_entity = {
            **existing,
            "kind": "npc",
            "name": name,
            "role": role,
            "description": public_bio,
            "public_bio": public_bio,
            "biography": biography,
            "visibility": "player_known",
            "location_id": _first_text(existing.get("location_id"), location_id),
            "entity_refs": aliases,
            "dossier_status": _first_text(existing.get("dossier_status"), "encountered"),
            "profile_authority": "campaign_bible",
            "provenance": {
                **_mapping(existing.get("provenance")),
                "last_source": "encountered_npc_profile_sync_v1",
                "first_seen_tick": _current_tick(session),
            },
        }
        if appearance:
            updated_entity.setdefault("appearance", appearance)
        if personality:
            updated_entity.setdefault("personality", personality)
        if speech_style:
            updated_entity.setdefault("speech_style", speech_style)
        for key in ("faction_ids", "values", "goals", "motives", "relationships", "knowledge_boundaries"):
            value = existing.get(key)
            if value in (None, "", [], {}):
                for profile in (session_profile, dynamic_profile, registry_profile):
                    candidate_value = profile.get(key)
                    if candidate_value not in (None, "", [], {}):
                        updated_entity[key] = deepcopy(candidate_value)
                        break
        if updated_entity != existing:
            entities[entity_id] = updated_entity
            changed = True
            if not existing:
                created.append(entity_id)
        else:
            entities[entity_id] = existing

        document = next(
            (
                row
                for row in documents
                if _document_matches_npc(row, entity_id, name)
            ),
            None,
        )
        if document is None:
            document_id = f"lore:npc:{_slug(name)}"
            occupied = {_text(row.get("document_id")) for row in documents}
            if document_id in occupied:
                document_id = f"{document_id}:{_slug(entity_id)}"
            details = [public_bio]
            if appearance:
                details.append(f"Appearance: {appearance}")
            if personality:
                details.append(f"Manner: {personality}")
            if speech_style:
                details.append(f"Speech: {speech_style}")
            full_text = "\n\n".join(details)
            documents.append(
                {
                    "document_id": document_id,
                    "topic_id": "npcs",
                    "title": name,
                    "full_text": full_text,
                    "summary_500": full_text[:500].rstrip(),
                    "summary_120": full_text[:120].rstrip(),
                    "keywords": [entity_id, runtime_npc_id, name, role, location_id],
                    "entity_refs": [entity_id, runtime_npc_id],
                    "entities": [entity_id],
                    "visibility": "player_known",
                    "canon_revision": revision,
                    "provenance": {
                        "source": "encountered_npc_profile_sync_v1",
                        "profile_authority": "campaign_bible",
                    },
                }
            )
            page_statuses[document_id] = "learned"
            changed = True
        entity_statuses[entity_id] = "learned"
        ensured.append(entity_id)

    if changed:
        candidate["canon_revision"] = revision
    candidate["entities"] = entities
    candidate["documents"] = documents
    discovery["pages"] = page_statuses
    discovery["entities"] = entity_statuses
    candidate["discovery_state"] = discovery
    return candidate, tuple(ensured), tuple(created), changed


def sync_encountered_npc_lore(
    session_id: str,
    session: Mapping[str, Any],
    *,
    explicit_npc_ids: Sequence[str] = (),
    database: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persist newly encountered NPC bios once and return the hydrated session."""

    npc_ids = encountered_npc_ids(session, explicit_npc_ids=explicit_npc_ids)
    if not npc_ids:
        return dict(session), {
            "mode": "no_encountered_npcs",
            "persisted": False,
            "encountered_npc_ids": [],
            "created_npc_ids": [],
            "changed": False,
        }
    campaign_id = _campaign_id(session_id, session)
    portable = _portable_bible(session)
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
                    engine_version="rpg-npc-lore-sync-v1",
                    schema_version=_text(manifest.get("schema_version")) or "rpg-session-v1",
                    seed=_text(manifest.get("seed") or setup.get("seed")) or "0",
                    metadata={"source": "encountered_npc_profile_sync_v1"},
                )
            current = work.campaign_bibles.get(context, campaign_id, for_update=True)
            bible = deepcopy(current["document"] if current is not None else portable)
            next_revision = int(current["revision"]) + 1 if current is not None else 1
            bible, ensured, created, changed = ensure_encountered_npc_lore(
                bible,
                session,
                explicit_npc_ids=npc_ids,
                canon_revision=next_revision,
            )
            stored = current
            if changed or current is None:
                bible["canon_revision"] = max(int(bible.get("canon_revision") or 0), next_revision)
                stored = work.campaign_bibles.put(
                    context,
                    campaign_id=campaign_id,
                    document=bible,
                    expected_revision=(int(current["revision"]) if current is not None else 0),
                    provenance={
                        **(_mapping(current.get("provenance")) if current is not None else {}),
                        "last_source": "encountered_npc_profile_sync_v1",
                        "encountered_npc_ids": list(ensured),
                        "created_npc_ids": list(created),
                    },
                    consistency_report=(
                        _mapping(current.get("consistency_report")) if current is not None else {}
                    ),
                    completeness=(
                        _mapping(current.get("completeness")) if current is not None else {}
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
        if changed:
            hydrated = _save_portable_projection(hydrated)
        return hydrated, {
            "mode": "postgresql_authority",
            "persisted": True,
            "campaign_id": campaign_id,
            "revision": int(stored["revision"]),
            "content_hash": str(stored["content_hash"]),
            "encountered_npc_ids": list(ensured),
            "created_npc_ids": list(created),
            "changed": changed,
        }
    except Exception as exc:
        bible, ensured, created, changed = ensure_encountered_npc_lore(
            portable,
            session,
            explicit_npc_ids=npc_ids,
        )
        digest = campaign_bible_hash(bible)
        fallback = _hydrate_session(
            session,
            bible,
            revision=int(bible.get("canon_revision") or 0),
            content_hash=digest,
        )
        if changed:
            fallback = _save_portable_projection(fallback)
        return fallback, {
            "mode": "portable_projection_fallback",
            "persisted": False,
            "campaign_id": campaign_id,
            "content_hash": digest,
            "encountered_npc_ids": list(ensured),
            "created_npc_ids": list(created),
            "changed": changed,
            "error": type(exc).__name__,
        }
