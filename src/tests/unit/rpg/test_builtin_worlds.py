"""The worlds Omnix ships with (RQ-2.8, roadmap §4.4): bundles built from readable source, like any shared world."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.apps.rpg.genesis.worlds.builtin_worlds import STARTER, bundle_bytes, installed_world_id
from app.apps.rpg.genesis.worlds.world_bundle import parse_world_bundle_archive

SOURCE = Path(__file__).resolve().parents[4] / "resources/examples/rpg/world-bundles/the-market-road"


def _materializer():
    spec = importlib.util.spec_from_file_location("materialize_the_market_road", SOURCE / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_starter_bundle_is_a_pure_function_of_its_source() -> None:
    """The bundle a workspace installs, and the one ``materialize.py`` writes, are the same bytes every build."""
    built = _materializer().build_bundle(SOURCE)
    assert built == bundle_bytes(STARTER) == _materializer().build_bundle(SOURCE)


def test_the_starter_world_is_certified_for_launch_with_its_openings() -> None:
    payload = parse_world_bundle_archive(bundle_bytes(STARTER)).payload
    [release] = payload.world_releases
    assert release["document"]["certification"]["launch_ready"] is True
    assert release["document"]["certification"]["missing_requirements"] == []
    places = {row["metadata"]["starting_place_key"] for row in payload.scenarios}
    assert places == {"rusty_flagon_tavern", "market_district", "northern_road", "old_quarry", "glimmerdeep_pass"}
    assert payload.world["metadata"]["default_scenario_id"] in {row["id"] for row in payload.scenarios}


def test_the_starter_world_authors_how_it_plays() -> None:
    source = json.loads((SOURCE / "world.source.json").read_text(encoding="utf-8"))
    canon = source["revision"]["canon"]
    people = {row["id"] for row in canon["characters"]}
    assert {row["provider_id"] for row in canon["economy"]["providers"]} <= people
    assert {row["npc_id"] for row in canon["routines"]} == people
    assert {row["npc_id"] for row in canon["knowledge"]} == people
    assert all(row.get("secrets") for row in canon["characters"])  # each keeps something to themselves
    assert all(row.get("environment") for row in source["revision"]["topology"]["locations"])


def test_a_newer_bundle_installs_beside_the_older_one() -> None:
    assert installed_world_id(STARTER).startswith("world:the-market-road-")
    assert len(installed_world_id(STARTER).rsplit("-", 1)[1]) == 12
