"""The world editor's page for how a world plays: its economy, routines, knowledge, pressures and bestiary (RQ-4.1).

The author's sections are a draft kept with the world (its metadata's ``play_sections``) until a publication writes
them into the new revision (``play_section_publication``). Before anything is saved the page shows what the latest
revision carries, so the draft starts from what plays today. Saving checks the draft's shape and refuses one
written over a newer save (``expected_content_hash``); references to people, places and items the world lacks are
shown as findings and stop the next publication, not the save. World Forge offers a first draft from the lore
(``play_section_generation``), which is not kept until the author saves it.

Readiness, for the editor and for launch: each section is ``authored`` (the world wrote it) or ``derived`` (launch
infers it from the lore), as published and as the draft would publish.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.persistence.unit_of_work import unit_of_work
from app.security.tenant_context import current_tenant

from .contracts import WorldRevisionDocument
from .generation_jobs import canonical_hash
from .lifecycle_service import require_world_writable
from .lore_sections import lore_rows
from .play_section_generation import generate_play_sections
from .play_section_publication import PLAY_SECTIONS_KEY
from .published_world_setup import published_locations
from .semantic_validation import play_section_release_findings
from .world_play_sections import (
    PlaySectionsDraft,
    authorship,
    draft_findings,
    parse_play_sections,
    play_sections_document,
    unknown_creatures,
    with_play_sections,
)


class PlaySectionsInvalidError(ValueError):
    """A draft whose shape is wrong; its findings name each error."""

    def __init__(self, findings: tuple[str, ...]):
        super().__init__("world_play_sections_invalid")
        self.findings = findings


def _text(value: Any) -> str:
    return str(value or "").strip()


def _revision(row: Mapping[str, Any] | None) -> WorldRevisionDocument | None:
    return WorldRevisionDocument.model_validate(row["document"]) if row is not None else None


def _stored(world: Mapping[str, Any]) -> dict[str, Any] | None:
    stored = dict(world.get("metadata") or {}).get(PLAY_SECTIONS_KEY)
    return dict(stored["document"]) if isinstance(stored, Mapping) and isinstance(stored.get("document"), Mapping) else None


def _plays(row: Any) -> bool:
    return isinstance(row, Mapping) and any(row.get(key) for key in ("stats", "behaviour", "loot"))


def _quest_plays(row: Any) -> bool:
    return isinstance(row, Mapping) and any(row.get(key) for key in ("steps", "giver_id", "deadline_hours"))


def _as_played(document: Mapping[str, Any]) -> str:
    """A draft's hash as it plays: a revision lists its creatures and quests in the lore's order, the draft in the
    author's, and a row that says nothing of how it fights (or how it is done) is no row at all."""
    bestiary = sorted((row for row in document.get("bestiary") or () if _plays(row)),
                      key=lambda row: _text(dict(row).get("id")))
    quests = sorted((row for row in document.get("quests") or () if _quest_plays(row)),
                    key=lambda row: _text(dict(row).get("id")))
    return canonical_hash({**dict(document), "bestiary": bestiary, "quests": quests})


def _published(revision: WorldRevisionDocument | None) -> dict[str, Any]:
    return play_sections_document(revision.canon if revision is not None else {})


def _references(revision: WorldRevisionDocument | None) -> dict[str, list[dict[str, str]]]:
    """What a section may name, for the editor's choices: the world's people, places, items, creatures, regions and
    quests as launch reads them."""
    if revision is None:
        return {key: [] for key in ("people", "places", "items", "creatures", "regions", "quests")}
    canon = dict(revision.canon)

    def named(rows: Any) -> list[dict[str, str]]:
        return sorted(
            ({"id": _text(row.get("id")), "name": _text(row.get("name")) or _text(row.get("id"))}
             for row in rows if _text(row.get("id"))),
            key=lambda row: (row["name"].casefold(), row["id"]),
        )

    places = published_locations(canon, dict(revision.topology), dict(revision.entity_manifest).get("locations") or ())
    return {
        "people": named(lore_rows(canon, "characters")),
        "places": named(places),
        "items": named(lore_rows(canon, "items")),
        "creatures": named(lore_rows(canon, "bestiary")),
        "regions": named(lore_rows(canon, "regions")),
        "quests": named(lore_rows(canon, "quests")),
    }


def _view(world: Mapping[str, Any], revision: WorldRevisionDocument | None) -> dict[str, Any]:
    published = _published(revision)
    stored = _stored(world)
    if stored is not None and "quests" not in stored:  # saved before quests were a section: the published ones
        stored = {**stored, "quests": published.get("quests") or []}
    document = stored if stored is not None else published
    draft = PlaySectionsDraft.model_validate(document)
    as_published = authorship(parse_play_sections(revision.canon)[0]) if revision is not None else None
    drafted_canon = with_play_sections(revision.canon if revision is not None else {}, draft)
    findings = (
        [*unknown_creatures(revision.canon, draft),
         *play_section_release_findings(revision.model_copy(update={"canon": drafted_canon}))]
        if revision is not None else []
    )
    return {
        "ok": True,
        "world_id": _text(world.get("id")),
        "document": draft.model_dump(mode="json"),  # every field, as the published contract types it
        "content_hash": canonical_hash(document),
        "saved": stored is not None,
        "unpublished": stored is not None and _as_played(stored) != _as_played(published),
        "published_revision": revision.revision if revision is not None else None,
        "readiness": {
            "published": as_published,
            "draft": authorship(parse_play_sections(drafted_canon)[0]),
        },
        "findings": findings,
        "references": _references(revision),
    }


def read_play_sections(world_id: str, *, database: Any | None = None) -> dict[str, Any]:
    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id)
        if world is None:
            work.rollback()
            raise KeyError(f"world_not_found:{world_id}")
        latest = work.world_scenarios.latest_world_revision(context, world_id)
        work.rollback()
    return _view(world, _revision(latest))


def save_play_sections(
    world_id: str,
    *,
    expected_content_hash: str,
    document: Any,
    database: Any | None = None,
) -> dict[str, Any]:
    """Keep the author's draft with the world; refused when its shape is wrong or a newer save is there."""
    draft, findings = draft_findings(document)
    if draft is None:
        raise PlaySectionsInvalidError(findings)
    written = draft.model_dump(mode="json", exclude_none=True)
    # A creature row that names no numbers, behaviour or loot is the creature as its lore has it: not kept.
    written["bestiary"] = [row for row in written.get("bestiary") or () if _plays(row)]
    context = current_tenant()
    with unit_of_work(database) as work:
        world = require_world_writable(work, context, world_id)
        latest = work.world_scenarios.latest_world_revision(context, world_id)
        stored = _stored(world)
        current = stored if stored is not None else _published(_revision(latest))
        if canonical_hash(current) != expected_content_hash:
            raise ValueError(f"world_play_sections_conflict:expected={expected_content_hash}:current={canonical_hash(current)}")
        metadata = {**dict(world.get("metadata") or {}), PLAY_SECTIONS_KEY: {"document": written}}
        work.world_scenarios.replace_world_metadata(context, world_id, metadata)
        world = work.world_scenarios.get_world(context, world_id)
        work.commit()
    return _view(world, _revision(latest))


def draft_play_sections_from_lore(world_id: str, *, database: Any | None = None) -> dict[str, Any]:
    """World Forge's first draft from the latest revision's lore; nothing is saved."""
    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id)
        if world is None:
            work.rollback()
            raise KeyError(f"world_not_found:{world_id}")
        latest = work.world_scenarios.latest_world_revision(context, world_id)
        work.rollback()
    revision = _revision(latest)
    if revision is None:
        raise ValueError(f"world_play_sections_need_a_published_revision:{world_id}")
    start = _text(dict(world.get("metadata") or {}).get("starting_location"))
    drafted = PlaySectionsDraft.model_validate(generate_play_sections(revision, start_location_id=start))
    return {"ok": True, "world_id": world_id, "document": drafted.model_dump(mode="json")}


def publish_play_sections(world_id: str, *, database: Any | None = None) -> dict[str, Any]:
    """Publish the world with the author's draft and pin each of its openings to it, so the next campaign plays it:
    each scenario is repaired at its starting place (``repair_world_for_launch``); a world whose openings are still
    only lore has them prepared (``prepare_opening_scenarios_for_launch``). A draft naming what the world lacks is
    refused there."""
    from .launch_repair_service import prepare_opening_scenarios_for_launch, repair_world_for_launch

    context = current_tenant()
    with unit_of_work(database) as work:
        if work.world_scenarios.get_world(context, world_id) is None:
            work.rollback()
            raise KeyError(f"world_not_found:{world_id}")
        pins = []
        for scenario in work.world_library.iter_scenarios(context, world_id=world_id):
            revisions = work.world_library.list_scenario_revisions(context, str(scenario["id"]))
            start = _text(dict(revisions[0]["document"]).get("starting_location_id")) if revisions else ""
            if start:
                pins.append((str(scenario["id"]), start))
        work.rollback()
    if pins:
        for scenario_id, start in pins:
            repair_world_for_launch(world_id, scenario_id=scenario_id, starting_location_id=start, database=database)
    else:
        prepare_opening_scenarios_for_launch(world_id, database=database)
    return read_play_sections(world_id, database=database)


__all__ = [
    "PlaySectionsInvalidError",
    "draft_play_sections_from_lore",
    "publish_play_sections",
    "read_play_sections",
    "save_play_sections",
]
