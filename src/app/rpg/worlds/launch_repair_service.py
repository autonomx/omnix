"""One-click recovery of a generated world and scenario for campaign launch."""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work

from .contracts import ScenarioRevisionDocument
from .generation_publication import (
    WorldGenerationPublication,
    compile_world_generation_publication,
)
from .map_blueprint_authoring import latest_ready_blueprint_requirements
from .map_blueprint_publication import merge_authored_blueprints
from .postgres_service import publish_scenario_revision
from .starter_bubble_service import promote_starter_bubble


def _existing_ready_promotion(
    world_id: str,
    *,
    starting_location_id: str,
    database: Any | None,
) -> dict[str, Any] | None:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        revisions = work.world_library.list_world_revisions(context, world_id)
        releases = work.world_library.list_world_releases(context, world_id)
        work.rollback()
    revision_by_number = {
        int(row.get("revision") or 0): row for row in revisions
    }
    for release in releases:
        release_document = dict(release.get("document") or {})
        certification = dict(release_document.get("certification") or {})
        if not bool(certification.get("launch_ready")):
            continue
        revision_number = int(release.get("world_revision") or 0)
        revision = revision_by_number.get(revision_number, {})
        revision_document = dict(revision.get("document") or {})
        starter = dict(
            dict(revision_document.get("provenance") or {}).get("starter_bubble")
            or {}
        )
        if str(starter.get("starting_location_id") or "") != starting_location_id:
            continue
        return {
            "world_id": world_id,
            "source_world_revision": int(starter.get("source_world_revision") or 0),
            "world_revision": revision_number,
            "world_revision_hash": str(revision.get("content_hash") or ""),
            "world_release": int(release.get("release") or 0),
            "world_release_hash": str(release.get("release_hash") or ""),
            "certification": certification,
            "reused": True,
        }
    return None


def _publish_repaired_world(
    world_id: str,
    *,
    starting_location_id: str,
    database: Any | None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id, for_update=True)
        if world is None:
            raise KeyError(f"world_not_found:{world_id}")
        runs = work.world_library.list_generation_runs(context, world_id=world_id)
        if not runs:
            raise ValueError(f"world_launch_repair_generation_missing:{world_id}")
        run = runs[0]
        topic_rows = work.world_generation.list_topics(
            context,
            world_id=world_id,
            draft_revision=int(run.get("draft_revision") or 1),
        )
        current_row = work.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM omnix_rpg_world_revisions "
            "WHERE workspace_id = %s AND world_id = %s",
            (context.workspace_id, world_id),
        ).fetchone()
        current_revision = int(current_row[0])
        compiled = compile_world_generation_publication(
            run=run,
            world=world,
            topic_rows=topic_rows,
            revision=current_revision + 1,
            starting_location_override=starting_location_id,
        )
        requirements = latest_ready_blueprint_requirements(work, context, world_id)
        revision, release = merge_authored_blueprints(
            compiled.world_revision,
            compiled.world_release,
            requirements,
        )
        compiled = WorldGenerationPublication(
            world_revision=revision,
            world_release=release,
            certification=dict(release.certification),
        )
        if not bool(compiled.certification.get("launch_ready")):
            missing = ",".join(
                str(value)
                for value in compiled.certification.get("missing_requirements") or ()
            )
            consistency = dict(compiled.certification.get("consistency_report") or {})
            issue_codes = Counter(
                str(issue.get("code") or "unknown")
                for issue in consistency.get("issues") or ()
                if isinstance(issue, dict)
            )
            findings = ",".join(
                f"{code}={count}" for code, count in issue_codes.most_common()
            )
            examples = ";".join(
                f"{issue.get('item_id')}:{issue.get('message')}"
                for issue in (consistency.get("issues") or ())[:5]
                if isinstance(issue, dict)
            )
            raise ValueError(
                f"world_launch_repair_incomplete:{missing or 'unknown'}"
                f":{findings or 'no_audit_details'}:{examples}"
            )
        stored_revision = work.world_scenarios.publish_world_revision(
            context,
            world_id=world_id,
            document=compiled.world_revision.model_dump(mode="json"),
            content_hash=compiled.world_revision.content_hash,
            expected_revision=current_revision,
        )
        stored_release = work.world_scenarios.publish_world_release(
            context,
            world_id=world_id,
            world_revision=int(stored_revision["revision"]),
            document=compiled.world_release.model_dump(mode="json"),
            release_hash=compiled.world_release.release_hash,
        )
        work.commit()
    return {
        "world_revision": int(stored_revision["revision"]),
        "world_revision_hash": str(stored_revision["content_hash"]),
        "world_release": int(stored_release["release"]),
        "world_release_hash": str(stored_release["release_hash"]),
        "certification": dict(compiled.certification),
    }


def repair_world_for_launch(
    world_id: str,
    *,
    scenario_id: str,
    starting_location_id: str,
    database: Any | None = None,
) -> dict[str, Any]:
    """Repair canon, materialize starter maps, and repin the selected scenario."""

    if not scenario_id.strip():
        raise ValueError("world_launch_repair_scenario_required")
    if not starting_location_id.strip():
        raise ValueError("world_launch_repair_starting_location_required")

    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        scenario = next(
            (
                row
                for row in work.world_library.list_scenarios(
                    context,
                    world_id=world_id,
                )
                if str(row.get("id") or "") == scenario_id
            ),
            None,
        )
        if scenario is None:
            raise KeyError(f"scenario_not_found:{scenario_id}")
        if str(scenario.get("world_id") or "") != world_id:
            raise ValueError(f"scenario_world_mismatch:{scenario_id}:{world_id}")
        revisions = work.world_library.list_scenario_revisions(context, scenario_id)
        work.rollback()

    promotion = _existing_ready_promotion(
        world_id,
        starting_location_id=starting_location_id,
        database=database,
    )
    repaired: dict[str, Any] = {}
    if promotion is None:
        repaired = _publish_repaired_world(
            world_id,
            starting_location_id=starting_location_id,
            database=database,
        )
        promoted_result = promote_starter_bubble(
            world_id=world_id,
            source_world_revision=int(repaired["world_revision"]),
            starting_location_id=starting_location_id,
            database=database,
        )
        promotion = dict(promoted_result.get("promotion") or {})
    promoted_revision = int(promotion.get("world_revision") or 0)
    promoted_release = int(promotion.get("world_release") or 0)
    promoted_hash = str(promotion.get("world_revision_hash") or "")
    release_document = dict(promotion.get("release_document") or {})
    final_certification = dict(
        promotion.get("certification")
        or release_document.get("certification")
        or {}
    )
    if not promoted_revision or not promoted_release or not promoted_hash:
        raise ValueError("world_launch_repair_map_promotion_failed")
    if not bool(final_certification.get("launch_ready")):
        raise ValueError("world_launch_repair_map_certification_failed")

    previous_document = dict(revisions[0].get("document") or {}) if revisions else {}
    if (
        revisions
        and int(previous_document.get("world_revision") or 0) == promoted_revision
        and int(previous_document.get("compatible_release") or 0) == promoted_release
        and str(previous_document.get("starting_location_id") or "")
        == starting_location_id
    ):
        return {
            "ok": True,
            "status": "ready",
            "reused": True,
            "world": repaired,
            "promotion": promotion,
            "scenario_revision": revisions[0],
            "certification": final_certification,
        }
    scenario_document = {
        **previous_document,
        "scenario_id": scenario_id,
        "revision": max((int(row.get("revision") or 0) for row in revisions), default=0) + 1,
        "world_id": world_id,
        "world_revision": promoted_revision,
        "world_revision_hash": promoted_hash,
        "compatible_release": promoted_release,
        "starting_epoch": str(previous_document.get("starting_epoch") or "Day 1"),
        "starting_location_id": starting_location_id,
        "activated_conflict_ids": list(previous_document.get("activated_conflict_ids") or ()),
        "initial_npc_ids": list(previous_document.get("initial_npc_ids") or ()),
        "protagonist_options": list(previous_document.get("protagonist_options") or ()),
        "starting_resources": dict(previous_document.get("starting_resources") or {}),
        "opening_seed_ids": list(previous_document.get("opening_seed_ids") or ()),
        "map_initialization": list(previous_document.get("map_initialization") or ()),
        "content_hash": "",
    }
    stored_scenario = publish_scenario_revision(
        ScenarioRevisionDocument.model_validate(scenario_document),
        database=database,
    )
    return {
        "ok": True,
        "status": "ready",
        "reused": False,
        "world": repaired,
        "promotion": promotion,
        "scenario_revision": stored_scenario,
        "certification": final_certification,
    }
