"""How a world plays, written in the world editor and published (RQ-4.1; PostgreSQL).

Aurelia is imported and adopted; its author takes World Forge's draft from the lore, sets a price, and saves it with
the world. Saving names a newer save, refuses a wrongly shaped draft, and shows what the world lacks. Publishing
republishes the world with the draft and pins its openings to it; the revision they launch from plays the price.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import current_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]

_AURELIA = Path(__file__).resolve().parents[3] / "resources/examples/rpg/world-bundles/aurelia-echoes-beyond-the-gate"


def _aurelia_bundle() -> bytes:
    spec = importlib.util.spec_from_file_location("aurelia_materialize", _AURELIA / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._build_bundle(_AURELIA)


def _pinned_revision(world_id: str):
    """The world revision the "Gateborn: First Light" opening launches from now."""
    from app.apps.rpg.genesis.worlds.contracts import WorldRevisionDocument

    with unit_of_work() as work:
        context = current_tenant()
        scenario = next(row for row in work.world_library.iter_scenarios(context, world_id=world_id)
                        if "gateborn" in str(row["id"]))
        pinned = dict(work.world_library.list_scenario_revisions(context, str(scenario["id"]))[0]["document"])
        row = work.world_scenarios.get_world_revision(context, world_id, int(pinned["world_revision"]))
        work.rollback()
    return WorldRevisionDocument.model_validate(row["document"]), pinned


def test_an_author_writes_how_the_world_plays_and_the_next_campaign_plays_it(tmp_path, monkeypatch) -> None:
    from app.apps.rpg.genesis.worlds.play_section_authoring import (
        PlaySectionsInvalidError,
        draft_play_sections_from_lore,
        publish_play_sections,
        read_play_sections,
        save_play_sections,
    )
    from app.apps.rpg.genesis.worlds.published_world_setup import session_world_model
    from app.apps.rpg.genesis.worlds.world_adoption import adopt_shared_world
    from app.apps.rpg.genesis.worlds.world_bundle_import import import_world_bundle

    monkeypatch.setenv("OMNIX_RESOURCES_DIR", str(tmp_path))
    world_id = f"world:aurelia-sections-{uuid.uuid4().hex[:10]}"
    imported = import_world_bundle(_aurelia_bundle(), target_world_id=world_id)
    adopt_shared_world(world_id, bundle_sha256=imported["bundle_sha256"])

    first = read_play_sections(world_id)
    assert not first["saved"] and first["published_revision"] is not None
    assert set(first["readiness"]["published"].values()) == {"derived"}  # Aurelia plays from its lore today
    assert first["references"]["people"] and first["references"]["places"]

    drafted = draft_play_sections_from_lore(world_id)["document"]
    provider = drafted["economy"]["providers"][0]
    provider["sells"][0]["price"] = {"gold": 7, "silver": 0, "copper": 0}
    saved = save_play_sections(world_id, expected_content_hash=first["content_hash"], document=drafted)
    assert saved["saved"] and saved["unpublished"] and saved["findings"] == []
    assert set(saved["readiness"]["draft"].values()) == {"authored"}
    assert set(saved["readiness"]["published"].values()) == {"derived"}  # not published yet

    with pytest.raises(ValueError, match="world_play_sections_conflict"):  # written over a newer save
        save_play_sections(world_id, expected_content_hash=first["content_hash"], document=drafted)
    with pytest.raises(PlaySectionsInvalidError) as invalid:
        save_play_sections(world_id, expected_content_hash=saved["content_hash"],
                           document={**drafted, "routines": [{"npc_id": ""}]})
    assert invalid.value.findings and invalid.value.findings[0].startswith("play_section_invalid:routines.0.npc_id:")

    lacking = save_play_sections(world_id, expected_content_hash=saved["content_hash"],
                                 document={**drafted, "routines": [*drafted["routines"], {"npc_id": "npc:nobody"}]})
    assert lacking["findings"] == ["play_section_unknown_person:routines:npc:nobody"]  # kept, and named
    with pytest.raises(ValueError, match="world_play_sections_invalid:play_section_unknown_person"):
        publish_play_sections(world_id)  # a publication refuses it
    saved = save_play_sections(world_id, expected_content_hash=lacking["content_hash"], document=drafted)

    published = publish_play_sections(world_id)
    assert published["saved"] and not published["unpublished"]
    assert set(published["readiness"]["published"].values()) == {"authored"}

    revision, pinned = _pinned_revision(world_id)
    assert revision.revision == published["published_revision"]
    played = session_world_model(revision, SimpleNamespace(starting_location_id=pinned["starting_location_id"]))
    assert played["authorship"]["economy"] == "authored"
    offer = provider["sells"][0]
    priced = next(row for row in played["offers"][provider["provider_id"]]
                  if row["offer_id"] == f"{provider['provider_id']}:{offer['offer_key']}")
    assert priced["price"] == {"gold": 7, "silver": 0, "copper": 0}
