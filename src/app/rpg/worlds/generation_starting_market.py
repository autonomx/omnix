"""Playable starting-market materialization for certified generated worlds."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class StartingMarketIssue:
    code: str
    entity_id: str
    path: str
    message: str
    evidence: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "entity_id": self.entity_id,
            "path": self.path,
            "message": self.message,
            "evidence": dict(self.evidence),
            "severity": "error",
            "blocking": True,
        }


class StartingMarketCompilationError(ValueError):
    def __init__(self, issues: Sequence[StartingMarketIssue]) -> None:
        self.issues = tuple(issues)
        rendered = ";".join(f"{row.code}:{row.entity_id}:{row.path}" for row in self.issues)
        super().__init__("starting_market_integrity_failed:" + rendered)


def _map(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict(row) for row in value if isinstance(row, Mapping))


def _candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("candidate", "content"):
        if isinstance(row.get(key), Mapping):
            return dict(row[key])
    return dict(row)


def _contract_enabled(topic_graph: Mapping[str, Any] | None) -> bool:
    graph = _map(topic_graph)
    contract = _map(_map(graph.get("metadata")).get("starting_market_contract"))
    if contract.get("required") or contract.get("domain_ids"):
        return True
    for node in _rows(graph.get("nodes")):
        fields = {
            str(row.get("field_id") or "")
            for row in _rows(_map(node.get("metadata")).get("field_definitions"))
        }
        if "vendor_inventory_item_ids" in fields:
            return True
    return False


def _entities(topic_rows: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, int, dict[str, Any]], ...]:
    values: list[tuple[str, int, dict[str, Any]]] = []
    for topic_index, raw in enumerate(topic_rows, 1):
        topic = _map(raw)
        candidate = _candidate(topic)
        topic_id = str(topic.get("topic_id") or candidate.get("topic_id") or f"topic:{topic_index}")
        values.extend((topic_id, index, row) for index, row in enumerate(_rows(candidate.get("entities"))))
    return tuple(values)


def _normalise(value: Any) -> str:
    rendered = str(value or "").strip().casefold()
    if ":" in rendered:
        rendered = rendered.split(":", 1)[-1]
    return "_".join(
        "".join(character if character.isalnum() else " " for character in rendered).split()
    )


def _ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _starting_place(
    places: Sequence[tuple[str, Mapping[str, Any]]],
    topic_graph: Mapping[str, Any] | None,
) -> str:
    metadata = _map(_map(topic_graph).get("metadata"))
    requested = _normalise(metadata.get("starting_location"))
    if not requested:
        return places[0][0] if places else ""
    matches = [
        place_id
        for place_id, place in places
        if requested in {_normalise(place_id), _normalise(place.get("name"))}
    ]
    return matches[0] if len(matches) == 1 else ""


def _price(item_id: str) -> int:
    digest = hashlib.sha256(f"price:{item_id}".encode()).hexdigest()
    return 5 + int(digest[:8], 16) % 196


def _stock(vendor_id: str, item_id: str) -> int:
    digest = hashlib.sha256(f"stock:{vendor_id}:{item_id}".encode()).hexdigest()
    return 1 + int(digest[:8], 16) % 6


def _empty_materialization(*, enabled: bool) -> dict[str, Any]:
    return {
        "schema_version": "rpg_world_starting_market_materialization_v1",
        "contract_enabled": enabled,
        "skipped": not enabled,
        "place_id": "",
        "vendors": [],
        "vendor_count": 0,
        "inventory_item_count": 0,
    }


def _materialize(
    topic_rows: Sequence[Mapping[str, Any]],
    topic_graph: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], tuple[StartingMarketIssue, ...]]:
    if not _contract_enabled(topic_graph):
        return _empty_materialization(enabled=False), ()
    entities = _entities(topic_rows)
    places = sorted(
        (str(row.get("id") or ""), row)
        for topic_id, _index, row in entities
        if topic_id == "places" and str(row.get("id") or "")
    )
    equipment = {
        str(row.get("id") or ""): row
        for topic_id, _index, row in entities
        if topic_id == "equipment_vehicles" and str(row.get("id") or "")
    }
    actors = [
        (str(row.get("id") or ""), index, row)
        for topic_id, index, row in entities
        if topic_id == "actors" and str(row.get("id") or "")
    ]
    hub_id = _starting_place(places, topic_graph)
    issues: list[StartingMarketIssue] = []
    if not hub_id:
        issues.append(StartingMarketIssue(
            "starting_market_place_unresolved", "", "/starting_market/place_id",
            "The playable starting market requires one unambiguous canonical starting place.",
            {"place_count": len(places)},
        ))
    vendors: list[dict[str, Any]] = []
    for actor_id, actor_index, actor in actors:
        if str(actor.get("location_id") or "") != hub_id:
            continue
        item_ids = _ids(actor.get("vendor_inventory_item_ids"))
        if not item_ids:
            continue
        invalid = sorted(value for value in item_ids if value not in equipment)
        if invalid:
            issues.append(StartingMarketIssue(
                "starting_vendor_inventory_reference_invalid", actor_id,
                f"/actors/entities/{actor_index}/vendor_inventory_item_ids",
                "Vendor inventory must reference canonical equipment or commodity definitions.",
                {"invalid_item_ids": invalid},
            ))
        valid_items = [value for value in item_ids if value in equipment][:5]
        if not valid_items:
            continue
        vendors.append({
            "vendor_id": actor_id,
            "place_id": hub_id,
            "inventory": [
                {"item_id": item_id, "price": _price(item_id), "quantity": _stock(actor_id, item_id)}
                for item_id in valid_items
            ],
        })
        if len(vendors) >= 2:
            break
    if hub_id and not vendors:
        issues.append(StartingMarketIssue(
            "starting_vendor_required", hub_id, "/starting_market/vendors",
            "The first playable location requires at least one canonical actor with usable stock.",
            {"actor_count": len(actors)},
        ))
    if vendors and not all(
        row["price"] > 0 and row["quantity"] > 0
        for vendor in vendors for row in vendor["inventory"]
    ):
        issues.append(StartingMarketIssue(
            "starting_vendor_stock_invalid", hub_id, "/starting_market/vendors",
            "Materialized prices and stock quantities must be positive.", {},
        ))
    return {
        "schema_version": "rpg_world_starting_market_materialization_v1",
        "contract_enabled": True,
        "skipped": False,
        "place_id": hub_id,
        "vendors": vendors,
        "vendor_count": len(vendors),
        "inventory_item_count": sum(len(vendor["inventory"]) for vendor in vendors),
    }, tuple(issues)


def starting_market_report(
    topic_rows: Sequence[Mapping[str, Any]],
    topic_graph: Mapping[str, Any] | None,
) -> dict[str, Any]:
    materialization, issues = _materialize(topic_rows, topic_graph)
    enabled = bool(materialization["contract_enabled"])
    return {
        "schema_version": "rpg_world_starting_market_report_v1",
        "passed": not issues,
        "issues": [row.as_dict() for row in issues],
        "materialization": materialization,
        "checks": {
            "contract_enabled": enabled,
            "skipped_when_not_declared": enabled or materialization["skipped"],
            "starting_place_resolved": not enabled or bool(materialization["place_id"]),
            "vendor_materialized": not enabled or materialization["vendor_count"] >= 1,
            "inventory_materialized": not enabled or materialization["inventory_item_count"] >= 1,
            "bounded_vendor_count": materialization["vendor_count"] <= 2,
            "bounded_inventory_count": materialization["inventory_item_count"] <= 10,
        },
    }


def require_valid_starting_market(
    topic_rows: Sequence[Mapping[str, Any]],
    topic_graph: Mapping[str, Any] | None,
) -> None:
    _materialization, issues = _materialize(topic_rows, topic_graph)
    if issues:
        raise StartingMarketCompilationError(issues)


__all__ = [
    "StartingMarketCompilationError",
    "StartingMarketIssue",
    "require_valid_starting_market",
    "starting_market_report",
]
