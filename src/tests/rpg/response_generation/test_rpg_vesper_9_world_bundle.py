from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

from app.rpg.worlds.world_bundle import parse_world_bundle_archive

BUNDLE_SHA256 = "41b3a7f7bdd17d38253034d07b50962f640545b1e920e329116a779ca55c89be"
SAMPLE_DIR = (
    Path(__file__).resolve().parents[4]
    / "examples"
    / "rpg"
    / "world-bundles"
    / "vesper-9-city-of-borrowed-minds"
)
EXPECTED_COUNTS = {
    "setting_rules": 1,
    "history_timeline": 5,
    "regions": 5,
    "places": 7,
    "groups": 6,
    "cultures": 4,
    "actors": 8,
    "networks": 4,
    "technology_augmentations": 6,
    "equipment_vehicles": 8,
    "roles_archetypes": 5,
    "threats": 6,
    "economy_law": 4,
    "pressures": 5,
    "quests": 6,
    "encounter_seeds": 6,
    "opening_threads": 3,
    "opening_scenarios": 2,
}


def _materializer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "vesper_9_world_bundle_materializer",
        SAMPLE_DIR / "materialize.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vesper_9_sample_world_bundle_is_import_ready(tmp_path: Path) -> None:
    output = tmp_path / "vesper-9.omnix-world.zip"
    materializer = _materializer()
    assert materializer.materialize_bundle(SAMPLE_DIR, output) == output
    content = output.read_bytes()
    assert hashlib.sha256(content).hexdigest() == BUNDLE_SHA256

    parsed = parse_world_bundle_archive(content)
    payload = parsed.payload
    topics = {row["topic_id"]: row for row in payload.topics}

    assert parsed.manifest.source_world_id == "world:vesper-9-city-of-borrowed-minds"
    assert parsed.manifest.assets == ()
    assert payload.world["title"] == "Vesper-9: City of Borrowed Minds"
    assert payload.world["genre"] == "cyberpunk"
    assert payload.world["metadata"]["image_generation"] == {
        "assets_included": False,
        "prompts_included": True,
    }
    assert set(topics) == set(EXPECTED_COUNTS)
    assert {
        topic_id: len(row["content"]["entities"])
        for topic_id, row in topics.items()
    } == EXPECTED_COUNTS
    assert sum(EXPECTED_COUNTS.values()) == 91

    for topic_id, row in topics.items():
        content = row["content"]
        assert row["status"] == "ready"
        assert content["image_prompts_only"] is True
        assert content["documents"][0]["full_text"].count("\n\n") >= 2
        for entity in content["entities"]:
            assert entity["description"].count("\n\n") >= 1
            if topic_id == "setting_rules":
                assert "image_prompt" not in entity
            else:
                assert len(entity["image_prompt"]) >= 240
                assert entity["image_role"]

    actors = topics["actors"]["content"]["entities"]
    assert all(actor["goal"] and actor["next_action"] for actor in actors)
    assert all(actor["reaction_conditions"] and actor["knowledge_limits"] for actor in actors)

    pressures = topics["pressures"]["content"]["entities"]
    assert all(pressure["next_tick_change"] for pressure in pressures)
    assert all(pressure["escalation_condition"] for pressure in pressures)
