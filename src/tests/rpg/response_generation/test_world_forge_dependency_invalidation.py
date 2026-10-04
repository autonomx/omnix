from __future__ import annotations

from dataclasses import dataclass

from app.rpg.worlds.generation_dependency_invalidation import (
    apply_stale_progress,
    build_retry_invalidation_records,
    dependent_topic_ids,
)


@dataclass(frozen=True)
class _Node:
    topic_id: str
    dependencies: tuple[str, ...] = ()


class _Graph:
    def __init__(self) -> None:
        self._nodes = (
            _Node("setting_rules"),
            _Node("regions", ("setting_rules",)),
            _Node("places", ("regions",)),
            _Node("actors", ("places",)),
            _Node("pressures", ("actors", "places")),
            _Node("opening_threads", ("pressures",)),
        )

    def topological_order(self) -> tuple[_Node, ...]:
        return self._nodes

    def node_map(self) -> dict[str, _Node]:
        return {node.topic_id: node for node in self._nodes}


def test_dependants_are_discovered_without_becoming_retry_targets() -> None:
    graph = _Graph()

    assert dependent_topic_ids(graph, ("places",)) == (
        "actors",
        "pressures",
        "opening_threads",
    )


def test_field_level_reference_change_invalidates_dependants() -> None:
    records = build_retry_invalidation_records(
        _Graph(),
        ("actors",),
        {"actors": {"scope": "entity_fields", "fields": ["group_ids"]}},
    )

    assert set(records) == {"pressures", "opening_threads"}
    assert records["pressures"]["required_action"] == "invalidate"
    assert records["pressures"]["automatically_regenerated"] is False
    assert records["pressures"]["caused_by_topic_ids"] == ["actors"]


def test_prose_level_change_requires_revalidation_not_regeneration() -> None:
    records = build_retry_invalidation_records(
        _Graph(),
        ("actors",),
        {"actors": {"scope": "entity_fields", "fields": ["personality"]}},
    )

    assert records["pressures"]["required_action"] == "revalidate"


def test_foundational_topic_replacement_marks_cascade_regeneration() -> None:
    records = build_retry_invalidation_records(
        _Graph(),
        ("setting_rules",),
        {"setting_rules": {"scope": "topic"}},
    )

    assert records["regions"]["required_action"] == "regenerate"
    assert records["opening_threads"]["required_action"] == "regenerate"


def test_stale_progress_is_publication_blocking() -> None:
    records = build_retry_invalidation_records(
        _Graph(),
        ("places",),
        {"places": {"scope": "entity_fields", "fields": ["sensory_profile"]}},
    )
    progress = apply_stale_progress({"publication_blocked": False}, records)

    assert progress["publication_blocked"] is True
    assert progress["stale_topic_ids"] == ["actors", "opening_threads", "pressures"]
    assert progress["stale_topics"]["actors"]["status"] == "potentially_stale"
