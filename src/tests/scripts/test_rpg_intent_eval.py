"""RQ-0.4: the intent corpus keeps its shape and the evaluation's own rules hold (no database, no model)."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("omnix_rpg_intent_eval_tests_target", ROOT / "scripts/rpg_intent_eval.py")
intent = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(intent)
CATALOG = json.loads((intent.CORPUS / "catalog.json").read_text(encoding="utf-8"))


def test_held_out_set_is_frozen_and_the_harness_refuses_a_changed_one(monkeypatch, tmp_path):
    intent.require_frozen_held_out()
    changed = tmp_path / "held_out.jsonl"
    changed.write_bytes(intent.HELD_OUT.read_bytes() + b"\n")
    monkeypatch.setattr(intent, "HELD_OUT", changed)
    with pytest.raises(SystemExit, match="frozen held-out set changed"):
        intent.require_frozen_held_out()
    # A Windows checkout that writes CRLF line endings is the same frozen file.
    crlf = tmp_path / "held_out_crlf.jsonl"
    lf = (intent.CORPUS / "held_out.jsonl").read_bytes().replace(b"\r\n", b"\n")
    crlf.write_bytes(lf.replace(b"\n", b"\r\n"))
    monkeypatch.setattr(intent, "HELD_OUT", crlf)
    intent.require_frozen_held_out()


def test_corpus_sizes_mix_and_labels():
    dev, held = intent.load_items("dev"), intent.load_items("held_out")
    assert (len(dev), len(held)) == (800, 1200)
    assert sum(not item["stateful"] for item in held) >= 800
    assert sum(item["target_entity"] is not None for item in held) >= 700
    rows = dev + held
    assert len({item["id"] for item in rows}) == 2000
    families = set(CATALOG["families"])
    for item in rows:
        world = CATALOG["worlds"][item["world"]]
        assert item["action_family"] in families
        assert item["scene"] in world["scenes"]
        assert item["target_entity"] is None or item["target_entity"] in world["entities"]
        # Labelled by the model, awaiting the owner's spot check, or relabelled by the owner (README, 2026-10-29).
        assert item["labelled_by"] == "model"
        assert item["review"] in {"pending_owner_spot_check", "owner_relabelled_2026-10-29"}
    counts = Counter(item["world"] for item in rows)
    assert min(counts.values()) >= 600
    tags = Counter(tag for item in rows for tag in item["tags"])
    for tag in ("typo", "multi_step", "question", "negation", "hypothetical", "trap:use", "trap:rest", "trap:hit",
                "trap:rent"):
        assert tags[tag] >= 5, tag


def test_catalog_resolves_ids_alias_ids_and_names():
    aurelia = intent.Catalog(CATALOG["worlds"]["aurelia"])
    assert aurelia.resolve("npc:liora-fen") == "npc:liora-fen"
    assert aurelia.resolve("guide where rhea is") == "npc:liora-fen"
    assert aurelia.resolve("healing_potion") == "npc:brindle-gearwing:healing-potion"
    assert aurelia.resolve("Lantern Bread") == "item:lantern-bread"
    assert aurelia.resolve("swordsmanship") == "skill:swordsmanship"
    assert aurelia.resolve("") is None and aurelia.resolve("a teapot") is None
    starter = intent.Catalog(CATALOG["worlds"]["starter"])
    assert starter.resolve("loc_tavern") == "location:rusty_flagon"
    assert starter.resolve("npc_guard_captain") == "npc:Aldric"


def _session(**player):
    base = {"location_id": "here", "currency": {"silver": 10}, "inventory_state": {"items": [
        {"item_id": "bread", "qty": 2}, {"item_id": "dagger", "qty": 1}]}, "skills": {"stealth": {"level": 0, "xp": 0}},
        "resources": {"hp": {"current": 100}}, "party_state": {"companions": []}}
    base.update(player)
    return {"simulation_state": {"player_state": base, "quest_state": {"quests": []}, "survival": {"fatigue": 5}},
            "runtime_state": {}}


@pytest.mark.parametrize("after,family,target", [
    ({"location_id": "there"}, "move", "there"),
    ({"currency": {"silver": 7}, "inventory_state": {"items": [{"item_id": "bread", "qty": 2},
                                                                {"item_id": "dagger", "qty": 1},
                                                                {"item_id": "potion", "qty": 1}]}}, "buy", "potion"),
    ({"currency": {"silver": 12}, "inventory_state": {"items": [{"item_id": "bread", "qty": 2}]}}, "sell", "dagger"),
    ({"inventory_state": {"items": [{"item_id": "bread", "qty": 1}, {"item_id": "dagger", "qty": 1}]}}, "drop", "bread"),
    ({"skills": {"stealth": {"level": 0, "xp": 10}}}, "practice", "skill:stealth"),
    ({"party_state": {"companions": [{"id": "npc:liora-fen"}]}}, "party", "npc:liora-fen"),
])
def test_material_changes_decide_the_observed_family(after, family, target):
    before, later = _session(), _session(**after)
    found = intent.changes(intent.material_state(before), intent.material_state(later))
    observed = intent.observed_reading(found, {"family": "talk", "target_ref": None}, later)
    assert (observed["family"], observed["target_ref"]) == (family, target)


def test_time_and_needs_drifting_are_not_material():
    before = _session()
    later = _session()
    later["simulation_state"]["survival"] = {"fatigue": 9, "hunger": 4}
    assert intent.changes(intent.material_state(before), intent.material_state(later)) == []
    assert intent.observed_reading([], {"family": "wait", "target_ref": None}, later) is None


def test_the_turn_is_scored_on_the_reading_it_ran_on():
    ran = {"mechanic": "talk", "family": "ask", "target_ref": "npc:liora"}
    assert intent.turn_reading(ran) == {"family": "ask", "target_ref": "npc:liora", "topics": []}
    question = {"mechanic": "clarify", "family": "buy", "target_ref": "item:rope"}
    assert intent.turn_reading(question) == {"family": "clarify", "target_ref": None}


def test_metrics_have_their_own_denominators():
    items = [
        {"id": "a", "action_family": "buy", "target_entity": "x", "stateful": True},
        {"id": "b", "action_family": "ask", "target_entity": None, "stateful": False},
        {"id": "c", "action_family": "talk", "target_entity": "y", "stateful": False},
    ]
    records = {
        "a": {"prediction": {"family": "buy", "stateful": False}, "correct": {"family": True, "target": True}, "static": {"gate": True}},
        "b": {"prediction": {"family": "talk", "stateful": True}, "correct": {"family": False, "target": None}, "static": {"gate": False}},
        "c": {"prediction": {"family": "talk", "stateful": False}, "correct": {"family": True, "target": False}, "static": {"gate": False}},
    }
    result = intent.metrics(items, records)
    assert result["action_family_accuracy"]["n"] == 3 and result["action_family_accuracy"]["successes"] == 2
    assert result["target_entity_accuracy"]["n"] == 2 and result["target_entity_accuracy"]["successes"] == 1
    assert result["false_stateful_rate"]["n"] == 2 and result["false_stateful_rate"]["successes"] == 1
    assert result["missed_stateful_rate"]["successes"] == 1
    assert 0 < result["false_stateful_rate"]["wilson_lower"] < 0.5 < result["false_stateful_rate"]["wilson_upper"]


def test_a_family_is_scored_by_the_mechanic_it_names() -> None:
    assert intent.same_family("look", "inspect") and intent.same_family("talk", "ask")
    assert intent.same_family("talk", "decline") and intent.same_family("ask", "ask")
    assert not intent.same_family("buy", "ask") and not intent.same_family("look", "move")


def test_an_unlisted_id_is_named_by_its_last_part() -> None:
    catalog = intent.Catalog({"entities": {
        "location:market": {"kind": "place", "names": ["the market"], "alias_ids": []},
        "location:old_road": {"kind": "place", "names": ["the old road"], "alias_ids": []},
        "npc:juno": {"kind": "person", "names": ["Juno Rask"], "alias_ids": []},
    }, "scenes": {}})
    assert catalog.resolve("location:market-road:northern-road") is None  # its region's slug is no market
    assert catalog.resolve("ent:actors:juno-rask") == "npc:juno"


def test_buying_the_thing_an_offer_sells_is_buying_the_offer() -> None:
    catalog = intent.Catalog({"entities": {
        "elara_torch": {"kind": "offer", "names": ["a torch", "a new torch"], "alias_ids": []},
        "torch": {"kind": "item", "names": ["torch"], "alias_ids": []},
        "rope": {"kind": "item", "names": ["rope"], "alias_ids": []},
    }, "scenes": {}})
    assert catalog.same_target("torch", "elara_torch") and catalog.same_target("elara_torch", "elara_torch")
    assert not catalog.same_target("rope", "elara_torch") and not catalog.same_target("elara_torch", "torch")


def test_a_quest_someone_offers_is_no_deed_of_the_heros_but_taking_it_is() -> None:
    before, offered, taken = _session(), _session(), _session()
    offered["simulation_state"]["quest_state"]["quests"] = [{"id": "quest:rats", "status": "available"}]
    taken["simulation_state"]["quest_state"]["quests"] = [{"id": "quest:rats", "status": "active"}]
    assert intent.changes(intent.material_state(before), intent.material_state(offered)) == []
    assert [change["kind"] for change in intent.changes(intent.material_state(offered),
                                                         intent.material_state(taken))] == ["quest_changed"]


def test_a_journey_set_out_for_a_place_further_off_is_a_move_to_that_place() -> None:
    found = [{"kind": "location", "to": "ent:places:null-chapel"}]
    meant = intent.observed_reading(found, {"family": "move", "target_ref": "ent:places:undertone"}, {})
    assert meant == {"family": "move", "target_ref": "ent:places:undertone"}  # arrived on the way there
    moved = intent.observed_reading(found, {"family": "talk", "target_ref": None}, {})
    assert moved == {"family": "move", "target_ref": "ent:places:null-chapel"}
