"""Soft archival lifecycle for reusable RPG world and scenario projects."""
from __future__ import annotations

from typing import Any

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


def require_world_writable(work: Any, context: Any, world_id: str) -> dict[str, Any]:
    world = work.world_scenarios.get_world(context, world_id, for_update=True)
    if world is None:
        raise KeyError(f"world_not_found:{world_id}")
    if world["status"] == "archived":
        raise ValueError(f"world_archived:{world_id}")
    return world


def _scenario_row(row: Any) -> dict[str, Any]:
    return {
        "workspace_id": str(row[0]),
        "id": str(row[1]),
        "world_id": str(row[2]),
        "title": str(row[3]),
        "description": str(row[4]),
        "status": str(row[5]),
        "metadata": dict(row[6]),
        "created_at": row[7].isoformat(),
        "updated_at": row[8].isoformat(),
    }


def _get_scenario(
    work: Any,
    context: Any,
    scenario_id: str,
    *,
    for_update: bool = False,
) -> dict[str, Any] | None:
    suffix = " FOR UPDATE" if for_update else ""
    row = work.connection.execute(
        "SELECT workspace_id, id, world_id, title, description, status, "
        "metadata_jsonb, created_at, updated_at FROM omnix_rpg_scenarios "
        "WHERE workspace_id = %s AND id = %s" + suffix,
        (context.workspace_id, scenario_id),
    ).fetchone()
    return _scenario_row(row) if row is not None else None


def require_scenario_writable(
    work: Any,
    context: Any,
    scenario_id: str,
) -> dict[str, Any]:
    scenario = _get_scenario(work, context, scenario_id, for_update=True)
    if scenario is None:
        raise KeyError(f"scenario_not_found:{scenario_id}")
    if scenario["status"] == "archived":
        raise ValueError(f"scenario_archived:{scenario_id}")
    require_world_writable(work, context, str(scenario["world_id"]))
    return scenario


def archive_world_project(
    world_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id, for_update=True)
        if world is None:
            raise KeyError(f"world_not_found:{world_id}")
        if world["status"] == "archived":
            work.rollback()
            return {"ok": True, "world": world, "idempotent": True}
        active = work.connection.execute(
            "SELECT run_id FROM omnix_rpg_world_generation_runs "
            "WHERE workspace_id = %s AND world_id = %s "
            "AND status IN ('planned', 'running') ORDER BY created_at LIMIT 1",
            (context.workspace_id, world_id),
        ).fetchone()
        if active is not None:
            raise ValueError(f"world_generation_active:{world_id}:{active[0]}")
        work.connection.execute(
            "UPDATE omnix_rpg_worlds SET status = 'archived', "
            "updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, world_id),
        )
        archived = work.world_scenarios.get_world(context, world_id)
        work.commit()
    return {"ok": True, "world": archived, "idempotent": False}


def restore_world_project(
    world_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id, for_update=True)
        if world is None:
            raise KeyError(f"world_not_found:{world_id}")
        if world["status"] != "archived":
            work.rollback()
            return {"ok": True, "world": world, "idempotent": True}
        published = work.connection.execute(
            "SELECT EXISTS(SELECT 1 FROM omnix_rpg_world_revisions "
            "WHERE workspace_id = %s AND world_id = %s)",
            (context.workspace_id, world_id),
        ).fetchone()[0]
        status = "published" if bool(published) else "draft"
        work.connection.execute(
            "UPDATE omnix_rpg_worlds SET status = %s, updated_at = CURRENT_TIMESTAMP "
            "WHERE workspace_id = %s AND id = %s",
            (status, context.workspace_id, world_id),
        )
        restored = work.world_scenarios.get_world(context, world_id)
        work.commit()
    return {"ok": True, "world": restored, "idempotent": False}


def archive_scenario_project(
    scenario_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        scenario = _get_scenario(work, context, scenario_id, for_update=True)
        if scenario is None:
            raise KeyError(f"scenario_not_found:{scenario_id}")
        if scenario["status"] == "archived":
            work.rollback()
            return {"ok": True, "scenario": scenario, "idempotent": True}
        work.connection.execute(
            "UPDATE omnix_rpg_scenarios SET status = 'archived', "
            "updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, scenario_id),
        )
        archived = _get_scenario(work, context, scenario_id)
        work.commit()
    return {"ok": True, "scenario": archived, "idempotent": False}


def restore_scenario_project(
    scenario_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        scenario = _get_scenario(work, context, scenario_id, for_update=True)
        if scenario is None:
            raise KeyError(f"scenario_not_found:{scenario_id}")
        if scenario["status"] != "archived":
            work.rollback()
            return {"ok": True, "scenario": scenario, "idempotent": True}
        require_world_writable(work, context, str(scenario["world_id"]))
        published = work.connection.execute(
            "SELECT EXISTS(SELECT 1 FROM omnix_rpg_scenario_revisions "
            "WHERE workspace_id = %s AND scenario_id = %s)",
            (context.workspace_id, scenario_id),
        ).fetchone()[0]
        status = "published" if bool(published) else "draft"
        work.connection.execute(
            "UPDATE omnix_rpg_scenarios SET status = %s, updated_at = CURRENT_TIMESTAMP "
            "WHERE workspace_id = %s AND id = %s",
            (status, context.workspace_id, scenario_id),
        )
        restored = _get_scenario(work, context, scenario_id)
        work.commit()
    return {"ok": True, "scenario": restored, "idempotent": False}
