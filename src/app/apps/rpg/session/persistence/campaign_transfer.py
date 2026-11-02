"""A campaign carried to another Omnix (RQ-8.6): exported as a save package, imported from one.

The package is format 8 (``build_campaign_save_package``): the campaign document as it loads, with its turns'
narrations. Its ``transfer`` section carries what the campaign plays from beside the document:

- its creation artifacts and its bible (the campaign's own lore);
- its binding to a world (the world, revision, release and opening it was launched from);
- its local maps as they stand, and its canonical narrative responses;
- the proposals still pending for its next turn to fold in (EV-11).

Importing writes all of it in one transaction, under the campaign's own id. A campaign already in this library is
refused (``rpg_campaign_already_in_library``): its ids run through its document, and a copy under another id is
not offered. A campaign bound to a world needs that world's revision and release here (installed from its
bundle) and, a world made elsewhere, adopted here (``rpg_campaign_world_not_adopted``), else it is refused
(``rpg_campaign_world_not_installed``); a document newer than this Omnix is refused as
everywhere (``rpg_campaign_requires_newer_omnix``, 503). The history of turns before the export stays behind: the
imported campaign starts its history at the revision it arrives with, kept whole as its first snapshot.
"""
from __future__ import annotations

from typing import Any, Mapping

from app.persistence.unit_of_work import unit_of_work

TRANSFER_VERSION = "rpg_campaign_transfer_v1"


class CampaignTransferRefused(ValueError):
    """An import this library cannot take; the message is its code and subject (``code:subject``)."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def export_campaign(session_id: str) -> dict[str, Any]:
    """The campaign as a save package with what it plays from; KeyError when it is not in this library."""
    from app.apps.rpg.foundation.persistence.package_builder import build_campaign_save_package
    from app.apps.rpg.session.persistence.session_records import _context, _database, load_session_from_postgres

    document = load_session_from_postgres(session_id)
    if document is None:
        raise KeyError(f"session_not_found:{session_id}")
    database = _database()
    context = _context(database)
    with unit_of_work(database) as work:
        artifacts = work.rpg.get_campaign_artifacts(context, session_id)
        bible = work.campaign_bibles.get(context, session_id)
        binding = work.world_scenarios.get_campaign_binding(context, session_id)
        maps = work.map_instances.list_instances(context, session_id)
        responses = work.narrative_responses.list_campaign(context, session_id, limit=2_000)
        proposals = work.rpg_proposals.pending(context, session_id, through_revision=2**31 - 1)
        work.rollback()
    package = build_campaign_save_package(document)
    package["transfer"] = {
        "format_version": TRANSFER_VERSION,
        "campaign_id": session_id,
        "creation_artifacts": artifacts,
        "campaign_bible": (
            {key: bible[key] for key in ("document", "provenance", "consistency_report", "completeness")}
            if bible is not None else None
        ),
        "world_binding": binding,
        "map_instances": [
            {key: row[key] for key in ("map_instance_id", "location_id", "map_id", "definition_revision",
                                       "definition_hash", "snapshot")}
            for row in maps
        ],
        "narrative_responses": [response.as_dict() for response in responses],
        "proposals": [{key: row[key] for key in ("proposal_id", "kind", "source", "reason", "payload")}
                      for row in proposals],
    }
    return package


def import_campaign(package: Any) -> dict[str, Any]:
    """Write the package's campaign into this library under its own id; the session as it now loads."""
    from app.apps.rpg.narration.narrative_engine.serialization import canonical_response_from_dict
    from app.apps.rpg.session.campaign_state import load_campaign_save_package
    from app.apps.rpg.session.persistence.session_records import (
        _campaign_id,
        _context,
        _database,
        load_session_from_postgres,
        save_session_to_postgres,
    )

    document = load_campaign_save_package(package)
    if document is None:
        raise CampaignTransferRefused("rpg_campaign_package_without_campaign:")
    transfer = _mapping(_mapping(package).get("transfer"))
    campaign_id = _campaign_id(document)
    binding = _mapping(transfer.get("world_binding"))
    bible = _mapping(transfer.get("campaign_bible"))
    database = _database()
    context = _context(database)
    with unit_of_work(database) as work:
        if work.rpg.get_campaign(context, campaign_id) is not None:
            raise CampaignTransferRefused(f"rpg_campaign_already_in_library:{campaign_id}")
        if binding:
            world_id = str(binding.get("world_id") or "")
            revision = int(binding.get("world_revision") or 0)
            release = int(binding.get("world_release") or 0)
            if (work.world_scenarios.get_world_revision(context, world_id, revision) is None
                    or work.world_scenarios.get_world_release(context, world_id, revision, release) is None):
                raise CampaignTransferRefused(f"rpg_campaign_world_not_installed:{world_id}")
            from app.apps.rpg.genesis.worlds.world_adoption import shared_world_state

            world = work.world_scenarios.get_world(context, world_id) or {}
            state = shared_world_state(world)
            if state["shared"] and not state["adopted"]:  # a world made elsewhere is played once it is adopted here
                raise CampaignTransferRefused(f"rpg_campaign_world_not_adopted:{world_id}")
        from app.apps.rpg.session.upgrades.hero_record import hydrate_hero

        save_session_to_postgres(hydrate_hero(document), work=work)
        for kind, artifact in sorted(_mapping(transfer.get("creation_artifacts")).items()):
            work.rpg.put_campaign_artifact(context, campaign_id=campaign_id, kind=kind, document=_mapping(artifact))
        if bible:
            work.campaign_bibles.put(
                context,
                campaign_id=campaign_id,
                document=_mapping(bible.get("document")),
                expected_revision=0,
                provenance={**_mapping(bible.get("provenance")), "imported": True},
                consistency_report=_mapping(bible.get("consistency_report")),
                completeness=_mapping(bible.get("completeness")),
            )
        if binding:
            work.world_scenarios.bind_campaign(
                context,
                campaign_id=campaign_id,
                world_id=str(binding["world_id"]),
                world_revision=int(binding["world_revision"]),
                world_release=int(binding["world_release"]),
                scenario_id=str(binding.get("scenario_id") or ""),
                scenario_revision=int(binding.get("scenario_revision") or 0),
                binding=binding,
            )
        from app.apps.rpg.session.site_maps import store_all_site_maps

        # The grids of the campaign's own sites (EV-10), rebuilt from its document, before the instances on them.
        store_all_site_maps(work, context, campaign_id=campaign_id, document=document)
        for row in transfer.get("map_instances") or ():
            row = _mapping(row)
            work.map_instances.create_instance(
                context,
                map_instance_id=str(row["map_instance_id"]),
                campaign_id=campaign_id,
                location_id=str(row["location_id"]),
                map_id=str(row["map_id"]),
                definition_revision=int(row["definition_revision"]),
                definition_hash=str(row["definition_hash"]),
                snapshot=_mapping(row.get("snapshot")),
            )
        for raw in transfer.get("narrative_responses") or ():
            work.narrative_responses.save(context, canonical_response_from_dict(_mapping(raw)))
        for row in transfer.get("proposals") or ():  # pending: the imported campaign's next turn folds them in
            row = _mapping(row)
            work.rpg_proposals.put(context, campaign_id=campaign_id, proposal_id=str(row["proposal_id"]),
                                   kind=str(row["kind"]), source=str(row["source"]), after_revision=0,
                                   payload=_mapping(row.get("payload")), reason=str(row.get("reason") or ""))
        work.commit()
    session = load_session_from_postgres(campaign_id)
    return {"ok": True, "session_id": campaign_id, "session": session}


__all__ = ["CampaignTransferRefused", "TRANSFER_VERSION", "export_campaign", "import_campaign"]
