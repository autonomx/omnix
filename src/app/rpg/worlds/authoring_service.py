"""User-facing projections for reusable-world authoring.

The authoring API intentionally projects durable topic JSON into stable document
and collection page contracts. The browser does not need to understand provider-
specific payload shapes, and player-facing session lore remains a separate API.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work
from app.rpg.session.genesis.world_forge_contract import build_campaign_topic_graph

from .library_service import read_world_detail
from .lifecycle_service import require_world_writable

_SYSTEM_SECTIONS: tuple[dict[str, Any], ...] = (
    {"id": "overview", "label": "Overview", "group": "workspace", "page_kind": "document"},
    {"id": "generation", "label": "World Generation", "group": "workspace", "page_kind": "document"},
    {"id": "images", "label": "Images", "group": "workspace", "page_kind": "collection"},
    {"id": "map", "label": "Map", "group": "world", "page_kind": "document"},
    {"id": "areas", "label": "Areas", "group": "world", "page_kind": "collection"},
    {"id": "points_of_interest", "label": "Points of Interest", "group": "world", "page_kind": "collection"},
    {"id": "races", "label": "Races", "group": "world", "page_kind": "collection"},
    {"id": "classes", "label": "Classes", "group": "world", "page_kind": "collection"},
    {"id": "monsters", "label": "Monsters", "group": "world", "page_kind": "collection"},
    {"id": "items", "label": "Items", "group": "world", "page_kind": "collection"},
    {"id": "spells", "label": "Spells", "group": "world", "page_kind": "collection"},
    {"id": "feats", "label": "Feats", "group": "world", "page_kind": "collection"},
    {"id": "quests", "label": "Quests", "group": "world", "page_kind": "collection"},
    {"id": "scenarios", "label": "Scenarios", "group": "game-master", "page_kind": "collection"},
    {"id": "map_blueprints", "label": "Map Blueprints", "group": "game-master", "page_kind": "collection"},
    {"id": "validation", "label": "Validation", "group": "game-master", "page_kind": "document"},
    {"id": "releases", "label": "Releases", "group": "game-master", "page_kind": "collection"},
    {"id": "history_revisions", "label": "Revision History", "group": "game-master", "page_kind": "collection"},
    {"id": "advanced", "label": "Advanced", "group": "game-master", "page_kind": "document"},
)

_WORLD_COLLECTION_CATEGORIES = {
    "regions",
    "factions",
    "locations",
    "npcs",
    "points_of_interest",
    "races",
    "classes",
    "monsters",
    "items",
    "spells",
    "feats",
    "quests",
}
_GAME_MASTER_COLLECTION_CATEGORIES = {
    "story",
    "encounter_seeds",
    "one_shots",
    "opening_scenarios",
}
_COLLECTION_CATEGORIES = _WORLD_COLLECTION_CATEGORIES | _GAME_MASTER_COLLECTION_CATEGORIES
_PIPELINE_CATEGORIES = {"compiler", "audit", "index", "bootstrap"}
_ENTITY_KEYS = (
    "entities",
    "regions",
    "areas",
    "points_of_interest",
    "locations",
    "characters",
    "npcs",
    "races",
    "classes",
    "factions",
    "monsters",
    "items",
    "spells",
    "feats",
    "quests",
    "encounter_seeds",
    "one_shots",
    "opening_scenarios",
)


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _text(value: Any, fallback: str = "") -> str:
    return str(value).strip() if value is not None and str(value).strip() else fallback


def _topic_entity_rows(content: Mapping[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for key in _ENTITY_KEYS:
        for row in _rows(content.get(key)):
            identity = _text(
                row.get("id")
                or row.get("entity_id")
                or row.get("location_id")
                or row.get("npc_id")
                or row.get("faction_id")
                or row.get("name")
                or row.get("title")
            )
            fingerprint = identity or json.dumps(row, sort_keys=True, default=str)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append(row)
    return rows


def _entity_count(content: Mapping[str, Any]) -> int:
    return len(_topic_entity_rows(content))


def _operational_status(
    topic_id: str,
    *,
    topic: Mapping[str, Any] | None,
    dependencies: Sequence[str],
    topics: Mapping[str, Mapping[str, Any]],
    active: set[str],
    failed: set[str],
) -> str:
    if topic_id in failed or (topic and _text(topic.get("status")) == "failed"):
        return "failed"
    if topic_id in active:
        return "generating"
    if topic and _text(topic.get("status")) == "stale":
        return "stale"
    if topic and _text(topic.get("status")) == "ready":
        return "complete"
    if any(_text(topics.get(dep, {}).get("status")) != "ready" for dep in dependencies):
        return "waiting"
    return "empty"


def _editorial_status(topic: Mapping[str, Any] | None) -> str:
    if topic is None:
        return "unreviewed"
    authoring = _record(_record(topic.get("provenance")).get("authoring"))
    if bool(authoring.get("generation_lock")):
        return "locked"
    if (
        _text(authoring.get("edit_state")) == "manually_edited"
        or _text(topic.get("source")) == "manual"
    ):
        return "manually_edited"
    if authoring.get("approved_at"):
        return "approved"
    return "needs_review"


def _graph_nodes(detail: Mapping[str, Any]) -> list[dict[str, Any]]:
    runs = list(detail.get("generation_runs") or [])
    latest_run = _record(runs[0]) if runs else {}
    nodes = _rows(_record(latest_run.get("graph")).get("nodes"))
    if nodes:
        return nodes
    world = _record(detail.get("world"))
    metadata = _record(world.get("metadata"))
    graph = build_campaign_topic_graph(
        campaign_template=_text(metadata.get("campaign_template"), "classic_fantasy"),
        genre=_text(world.get("genre"), "classic_fantasy"),
        tone=_text(world.get("tone"), "heroic adventure"),
        depth="standard",
        background_expansion=True,
    )
    return [node.as_dict() for node in graph.nodes]


def _system_status(section_id: str, detail: Mapping[str, Any]) -> tuple[str, int]:
    if section_id == "overview":
        return "complete", 1
    if section_id == "generation":
        runs = list(detail.get("generation_runs") or [])
        if not runs:
            return "empty", 0
        status = _text(_record(runs[0]).get("status"), "empty")
        return ("generating" if status in {"planned", "running"} else status), 1
    collections = {
        "map_blueprints": list(detail.get("map_blueprints") or []),
        "scenarios": list(detail.get("scenarios") or []),
        "releases": list(detail.get("releases") or []),
        "history_revisions": list(detail.get("revisions") or []),
    }
    if section_id in collections:
        count = len(collections[section_id])
        return ("complete" if count else "empty"), count
    if section_id == "validation":
        releases = list(detail.get("releases") or [])
        return ("complete" if releases else "waiting"), len(releases)
    return "empty", 0


def _section_group(category: str) -> str:
    if category in _PIPELINE_CATEGORIES or category in _GAME_MASTER_COLLECTION_CATEGORIES:
        return "game-master"
    if category in _WORLD_COLLECTION_CATEGORIES:
        return "world"
    return "lore"


def read_authoring_manifest(
    world_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    detail = read_world_detail(world_id, database=database)
    topics = {str(row["topic_id"]): row for row in detail["topics"]}
    latest_run = _record(detail["generation_runs"][0]) if detail["generation_runs"] else {}
    progress = _record(latest_run.get("progress"))
    active = {_text(value) for value in progress.get("active_topic_ids") or []}
    failed = {_text(value) for value in progress.get("failed_topic_ids") or []}
    sections: list[dict[str, Any]] = []
    graph_ids: set[str] = set()
    for node in _graph_nodes(detail):
        topic_id = _text(node.get("topic_id"))
        if not topic_id:
            continue
        graph_ids.add(topic_id)
        topic = topics.get(topic_id)
        dependencies = [
            _text(value) for value in node.get("dependencies") or [] if _text(value)
        ]
        category = _text(node.get("category"), "lore")
        metadata = _record(node.get("metadata"))
        is_collection = category in _COLLECTION_CATEGORIES
        sections.append(
            {
                "id": topic_id,
                "label": _text(
                    node.get("title"),
                    topic_id.replace("_", " ").title(),
                ),
                "group": _section_group(category),
                "page_kind": "collection" if is_collection else "document",
                "topic_ids": [topic_id],
                "entity_kind": _text(
                    metadata.get("entity_kind"),
                    category[:-1] if category.endswith("s") else category,
                ),
                "dependencies": dependencies,
                "required_before_launch": bool(
                    node.get("required_before_launch", True)
                ),
                "supports_generation": category not in _PIPELINE_CATEGORIES,
                "supports_images": is_collection or topic_id in {
                    "realm",
                    "regions",
                    "locations",
                },
                "supports_entity_editing": is_collection,
                "operational_status": _operational_status(
                    topic_id,
                    topic=topic,
                    dependencies=dependencies,
                    topics=topics,
                    active=active,
                    failed=failed,
                ),
                "editorial_status": _editorial_status(topic),
                "entity_count": (
                    _entity_count(_record(topic.get("content"))) if topic else 0
                ),
            }
        )
    for section in _SYSTEM_SECTIONS:
        if section["id"] in graph_ids:
            continue
        status, count = _system_status(str(section["id"]), detail)
        sections.append(
            {
                **section,
                "topic_ids": [],
                "dependencies": [],
                "required_before_launch": False,
                "supports_generation": False,
                "supports_images": section["id"] == "images",
                "supports_entity_editing": False,
                "operational_status": status,
                "editorial_status": "unreviewed",
                "entity_count": count,
            }
        )
    return {
        "ok": True,
        "world": detail["world"],
        "sections": sections,
        "generation": latest_run,
    }


def _entity_card(
    row: Mapping[str, Any],
    *,
    kind: str,
    index: int,
) -> dict[str, Any]:
    entity_id = _text(
        row.get("id")
        or row.get("entity_id")
        or row.get("location_id")
        or row.get("npc_id")
        or row.get("faction_id"),
        f"{kind}:{index + 1}",
    )
    title = _text(
        row.get("name") or row.get("title") or row.get("label"),
        entity_id.replace("_", " ").title(),
    )
    summary = _text(
        row.get("summary")
        or row.get("description")
        or row.get("role")
        or row.get("personality")
        or row.get("sensory_profile"),
        "No summary yet.",
    )
    return {
        "id": entity_id,
        "title": title,
        "summary": summary,
        "kind": kind,
        "image_target_id": f"{kind}:{entity_id}",
        "metadata": dict(row),
    }


def _document_blocks(content: Mapping[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for document in _rows(content.get("documents")):
        title = _text(document.get("title") or document.get("name"), "Lore")
        body = _text(
            document.get("full_text")
            or document.get("body")
            or document.get("text")
            or document.get("summary")
        )
        if body:
            blocks.append({"kind": "section", "title": title, "body": body})
    facts = _rows(content.get("facts"))
    if facts:
        blocks.append({"kind": "facts", "title": "Canon facts", "items": facts})
    if not blocks:
        blocks.append(
            {"kind": "json", "title": "Structured canon", "value": dict(content)}
        )
    return blocks


def read_authoring_section(
    world_id: str,
    section_id: str,
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    detail = read_world_detail(world_id, database=database)
    topic = next(
        (
            row
            for row in detail["topics"]
            if str(row["topic_id"]) == section_id
        ),
        None,
    )
    if topic is not None:
        content = _record(topic.get("content"))
        entities = _topic_entity_rows(content)
        if entities:
            kind = _text(entities[0].get("kind"), section_id.rstrip("s"))
            return {
                "ok": True,
                "section_id": section_id,
                "page_kind": "collection",
                "title": section_id.replace("_", " ").title(),
                "entities": [
                    _entity_card(row, kind=kind, index=index)
                    for index, row in enumerate(entities)
                ],
                "filters": [],
                "sort_options": ["name"],
                "topic": topic,
            }
        return {
            "ok": True,
            "section_id": section_id,
            "page_kind": "document",
            "title": section_id.replace("_", " ").title(),
            "summary": _text(
                content.get("summary") or content.get("description")
            ),
            "body": _document_blocks(content),
            "related_entities": [],
            "topic": topic,
        }
    if section_id == "overview":
        world = detail["world"]
        return {
            "ok": True,
            "section_id": section_id,
            "page_kind": "document",
            "title": world["title"],
            "summary": world.get("description") or "No description yet.",
            "body": [
                {
                    "kind": "facts",
                    "title": "World settings",
                    "items": [
                        {"label": "Genre", "value": world.get("genre")},
                        {"label": "Tone", "value": world.get("tone")},
                        {
                            "label": "Draft revision",
                            "value": world.get("draft_revision"),
                        },
                    ],
                }
            ],
            "related_entities": [],
        }
    collection_map = {
        "scenarios": detail["scenarios"],
        "map_blueprints": detail["map_blueprints"],
        "releases": detail["releases"],
        "history_revisions": detail["revisions"],
    }
    if section_id in collection_map:
        rows = [_record(row) for row in collection_map[section_id]]
        return {
            "ok": True,
            "section_id": section_id,
            "page_kind": "collection",
            "title": section_id.replace("_", " ").title(),
            "entities": [
                _entity_card(row, kind=section_id.rstrip("s"), index=index)
                for index, row in enumerate(rows)
            ],
            "filters": [],
            "sort_options": ["name"],
        }
    return {
        "ok": True,
        "section_id": section_id,
        "page_kind": "document",
        "title": section_id.replace("_", " ").title(),
        "summary": "This section has not been generated yet.",
        "body": [],
        "related_entities": [],
    }


def update_world_metadata(
    world_id: str,
    *,
    expected_draft_revision: int,
    changes: Mapping[str, Any],
    database: Any | None = None,
) -> dict[str, Any]:
    context = bootstrap_local_tenant(database)
    with unit_of_work(database) as work:
        world = require_world_writable(work, context, world_id)
        current_revision = int(world["draft_revision"])
        if current_revision != int(expected_draft_revision):
            raise ValueError(
                "world_draft_revision_conflict:"
                f"expected={expected_draft_revision}:current={current_revision}"
            )
        metadata = {
            **_record(world.get("metadata")),
            **_record(changes.get("metadata")),
        }
        values = {
            "title": _text(changes.get("title"), _text(world.get("title"))),
            "description": _text(
                changes.get("description"), _text(world.get("description"))
            ),
            "genre": _text(
                changes.get("genre"),
                _text(world.get("genre"), "classic_fantasy"),
            ),
            "tone": _text(
                changes.get("tone"),
                _text(world.get("tone"), "heroic adventure"),
            ),
            "seed": int(changes.get("seed", world.get("seed") or 0)),
        }
        updated = work.connection.execute(
            "UPDATE omnix_rpg_worlds SET title = %s, description = %s, "
            "genre = %s, tone = %s, seed = %s, metadata_jsonb = %s::jsonb, "
            "updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND id = %s "
            "AND draft_revision = %s RETURNING id",
            (
                values["title"],
                values["description"],
                values["genre"],
                values["tone"],
                values["seed"],
                json.dumps(metadata, sort_keys=True),
                context.workspace_id,
                world_id,
                current_revision,
            ),
        ).fetchone()
        if updated is None:
            raise ValueError("world_metadata_compare_and_swap_failed")
        stored = work.world_scenarios.get_world(context, world_id)
        work.commit()
    return {"ok": True, "world": stored}
