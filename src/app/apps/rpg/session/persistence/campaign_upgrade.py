"""Upgrading a stored campaign to the current document version, as a system turn (RQ-1.1, roadmap §4.2).

A campaign stored at an older document version is upgraded the first time it is opened, once:

1. its current state is pinned as the snapshot at its revision R: the pre-upgrade backup, which retention
   never deletes (RQ-1.7);
2. what its creation produced and no turn reads (``campaign_state.creation_artifacts``) is stored once, outside
   the document, in ``omnix_rpg_campaign_artifacts``;
3. the document is upcast (``campaign_state.upcast_campaign_document``) and committed as a ``system`` turn at
   R+1: a turn row with ``document_version`` set, the v5-to-v6 patch, and in its effects the inventory
   differences the merge resolved (for the owner's review, Q-2);
4. the upgraded state is pinned as the snapshot at R+1, so a v6 replay starts there.

The upgrade takes the campaign row lock for its own transaction only; two openers race to the lock and the
second finds the campaign current.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from app.persistence.unit_of_work import unit_of_work

logger = logging.getLogger(__name__)

_COMPACT_DIFF_LIMIT = 20


def _system_ids(campaign_id: str, version: int) -> dict[str, str]:
    return {
        "turn_id": f"turn:{campaign_id}:system:document-v{version}",
        "submission_id": f"system:document-v{version}",
        "interaction_id": f"interaction:{campaign_id}:system:document-v{version}",
    }


def upgrade_campaign_document(campaign_id: str, *, database: Any | None = None) -> dict[str, Any] | None:
    """Upgrade the stored campaign to the current document version as a system turn; None when it is current.

    A document newer than this code raises ``NewerCampaignDocumentError`` (RQ-1.7).
    """
    from app.apps.rpg.session.campaign_state import (
        CURRENT_SCHEMA_VERSION,
        NewerCampaignDocumentError,
        creation_artifacts,
        merge_inventories,
        schema_version,
        split_creation_artifacts,
        upcast_campaign_document,
    )
    from app.apps.rpg.session.persistence.session_records import _context, _database

    database = database or _database()
    context = _context(database)
    with unit_of_work(database) as work:
        campaign = work.rpg.get_campaign(context, campaign_id, for_update=True)
        if campaign is None:
            work.rollback()
            return None
        stored = dict(campaign["state"])
        version = schema_version(stored)
        if version > CURRENT_SCHEMA_VERSION:
            work.rollback()
            raise NewerCampaignDocumentError(version)
        if version == CURRENT_SCHEMA_VERSION:
            work.rollback()
            return None

        revision = int(campaign["revision"])
        backup = work.rpg.pin_current_state(context, campaign_id=campaign_id, document_version=version)
        artifacts = creation_artifacts(stored)
        for kind, document in sorted(artifacts.items()):
            work.rpg.put_campaign_artifact(context, campaign_id=campaign_id, kind=kind, document=document)
        _, differences = merge_inventories(deepcopy(stored))
        upgraded, _ = split_creation_artifacts(upcast_campaign_document(deepcopy(stored)))
        runtime = upgraded.setdefault("runtime_state", {})
        runtime["state_revision"] = revision + 1

        ids = _system_ids(campaign_id, CURRENT_SCHEMA_VERSION)
        upgrade = {
            "kind": "system",
            "type": "document_upgrade",
            "from_document_version": version,
            "to_document_version": CURRENT_SCHEMA_VERSION,
        }
        committed = work.rpg.commit_turn(
            context,
            campaign_id=campaign_id,
            turn_id=ids["turn_id"],
            submission_id=ids["submission_id"],
            interaction_id=ids["interaction_id"],
            expected_revision=revision,
            command=upgrade,
            next_state=upgraded,
            canonical_effects={
                **upgrade,
                "pinned_backup_revision": revision,
                "artifacts_moved_out": sorted(artifacts),
                "inventory_differences": differences,
            },
            interaction_event={**upgrade, "type": "document_upgraded"},
            compact_response={
                "ok": True,
                **upgrade,
                "inventory_differences": differences[:_COMPACT_DIFF_LIMIT],
                "inventory_differences_total": len(differences),
            },
            engine_version=str(campaign.get("engine_version") or "rpg-engine"),
            schema_version=str(campaign.get("schema_version") or "rpg-session-v1"),
            locked_campaign=campaign,
        )
        snapshot = work.rpg.create_snapshot(
            context,
            campaign_id=campaign_id,
            snapshot_id=f"snapshot:{campaign_id}:{revision + 1}",
            revision=revision + 1,
            state=upgraded,
            state_hash_value=committed["campaign"]["state_hash"],
            engine_version=str(campaign.get("engine_version") or "rpg-engine"),
            schema_version=str(campaign.get("schema_version") or "rpg-session-v1"),
            pinned=True,
            document_version=CURRENT_SCHEMA_VERSION,
        )
        work.commit()
    logger.info(
        "rpg_campaign_document_upgraded campaign=%s revision=%s from=%s to=%s differences=%s artifacts=%s",
        campaign_id, revision + 1, version, CURRENT_SCHEMA_VERSION, len(differences), sorted(artifacts),
    )
    return {
        "campaign_id": campaign_id,
        "from_document_version": version,
        "to_document_version": CURRENT_SCHEMA_VERSION,
        "revision": revision + 1,
        "backup_snapshot": backup,
        "upgrade_snapshot_id": snapshot["id"],
        "artifacts_moved_out": sorted(artifacts),
        "inventory_differences": differences,
        "state": upgraded,
    }


def upgrade_all_campaigns(*, database: Any | None = None) -> list[dict[str, Any]]:
    """Upgrade every campaign of the current workspace that is stored at an older version (the operator's batch)."""
    from app.apps.rpg.session.persistence.session_records import _context, _database

    database = database or _database()
    context = _context(database)
    results = []
    after = ""
    while True:
        # A page at a time, by id, so a large workspace never loads every campaign id at once.
        with unit_of_work(database) as work:
            campaign_ids = [str(row[0]) for row in work.connection.execute(
                "SELECT id FROM omnix_rpg_campaigns WHERE workspace_id = %s AND id > %s "
                "AND COALESCE((state_jsonb #>> '{manifest,schema_version}')::int, 1) < %s ORDER BY id LIMIT %s",
                (context.workspace_id, after, _current_version(), _UPGRADE_PAGE),
            ).fetchall()]
            work.rollback()
        for campaign_id in campaign_ids:
            upgraded = upgrade_campaign_document(campaign_id, database=database)
            if upgraded is not None:
                results.append({key: value for key, value in upgraded.items() if key != "state"})
        if len(campaign_ids) < _UPGRADE_PAGE:
            return results
        after = campaign_ids[-1]


_UPGRADE_PAGE = 100


def _current_version() -> int:
    from app.apps.rpg.session.campaign_state import CURRENT_SCHEMA_VERSION

    return CURRENT_SCHEMA_VERSION
