"""The game master (evolution roadmap EV-0, part 1): its bounds, the rules that fold its proposals in, the checks on
what it proposes, and the checks on what its panel says."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from app.apps.rpg.foundation.state import changes as c
from app.apps.rpg.foundation.state.reducer import reduce
from app.apps.rpg.narration.game_master.direction_call import checked
from app.apps.rpg.narration.game_master.panel import WITHHELD, answer_is_safe, known_view
from app.apps.rpg.rules import direction
from app.apps.rpg.rules.consequences import fold_complication, fold_fact
from app.apps.rpg.rules.routines import fold_move
from app.apps.rpg.session.campaign_state import upcast_campaign_document

FIXTURE = Path(__file__).resolve().parents[2] / "rpg" / "fixtures" / "campaign_documents_v5" / "aurelia.json.gz"
LIORA = "npc:liora-fen"


SECRET = "she hears the Meridian Gate whisper the protagonist's true Earth name"


def _document() -> dict:
    document = upcast_campaign_document(json.loads(gzip.decompress(FIXTURE.read_bytes())))
    document["simulation_state"]["world_model"]["npcs"][LIORA]["secrets"] = [SECRET]
    return document


def test_a_meaningful_event_resets_the_stall_and_the_upgrade_starts_from_the_present_turn() -> None:
    document = _document()
    simulation = document["simulation_state"]
    turns = int(document["state"].get("turn_count") or 0)
    assert simulation["direction"]["last_event_turn"] == turns and direction.stall(simulation, turns + 5) == 5
    assert direction.tracked(simulation, [c.TimeAdvanced(ticks=1, minutes=10)], turns + 5) == []
    noted = direction.tracked(simulation, [c.FactSet(fact_id="x", value=True)], turns + 5)
    after, _ = reduce(document, noted)
    assert direction.stall(after["simulation_state"], turns + 5) == 0
    assert direction.meaningful([c.PurseChanged(delta_copper=50, reason="a reward")])
    assert not direction.meaningful([c.PurseChanged(delta_copper=50, reason="sold the dagger")])


def test_the_game_masters_events_keep_the_days_limit_and_a_scenes_one_complication() -> None:
    document = _document()
    first = fold_complication(document, {"told": "A storm rolls in over the grove."})
    assert not first.refused
    document, _ = reduce(document, first.changes)
    again = fold_complication(document, {"told": "Another storm."})
    assert again.refused == "this scene already had its complication"
    for index in range(direction.EVENTS_PER_DAY - 1):
        done = fold_fact(document, {"fact": f"omen_{index}", "value": True, "told": "An omen."})
        assert not done.refused, done.refused
        document, _ = reduce(document, done.changes)
    assert fold_fact(document, {"fact": "omen_more", "value": True}).refused.startswith("the day's limit")


def test_a_fact_that_contradicts_one_that_holds_is_dropped() -> None:
    document, _ = reduce(_document(), [c.FactSet(fact_id="gate_fate", value="closed")])
    assert fold_fact(document, {"fact": "gate_fate", "value": "open"}).refused.startswith("it contradicts gate_fate")
    # The same value is no contradiction, but it is already so: folded again it would fire its effects twice.
    assert fold_fact(document, {"fact": "gate_fate", "value": "closed"}).refused == "gate_fate already holds"


def test_a_protected_person_is_never_moved_without_the_hero() -> None:
    document = _document()
    simulation = document["simulation_state"]
    simulation["player_state"]["party_state"] = {"companions": [{"npc_id": LIORA, "name": "Liora Fen"}]}
    place = next(iter(simulation["world_model"]["locations"]))
    assert LIORA in direction.protected(simulation)
    assert fold_move(document, {"npc_id": LIORA, "location_id": place}).refused.startswith("a protected person")
    other = next(npc for npc in simulation["world_model"]["npcs"] if npc not in direction.protected(simulation))
    assert not fold_move(document, {"npc_id": other, "location_id": place}).refused


def test_what_the_game_master_proposes_is_checked_before_it_is_stored() -> None:
    document = _document()
    secret = SECRET
    kept, dropped = checked(document, [
        {"kind": "gm_fact", "payload": {"fact": "rain", "value": True, "told": "Rain comes."}, "reason": "pace"},
        {"kind": "gm_rewrite_world", "payload": {}, "reason": "?"},
        {"kind": "gm_quest_offer", "payload": {"quest_id": "quest:no-such"}, "reason": "?"},
        {"kind": "gm_complication", "payload": {"told": secret}, "reason": "drama"},
    ])
    assert [row["kind"] for row in kept] == ["gm_fact"]
    assert dropped == ["gm_rewrite_world: no kind the record folds in", "gm_quest_offer: no such quest",
                       "gm_complication: it names a secret"]


def test_the_panel_knows_only_what_the_hero_knows_and_says_no_secret() -> None:
    document = _document()
    simulation = document["simulation_state"]
    known = known_view(document)["known"]
    assert set(known) <= set(simulation["hero_knowledge"]["entries"])
    unknown = next(row["name"] for npc_id, row in simulation["world_model"]["npcs"].items() if npc_id not in known)
    secret = SECRET
    assert answer_is_safe(document, "You stand in the grove; go to the village next.")
    assert not answer_is_safe(document, f"Seek out {unknown}.")  # someone the hero has not met or heard of
    assert not answer_is_safe(document, f"Liora knows this: {secret}.")
    assert "secrets" not in json.dumps(known_view(document))
    assert WITHHELD


def test_a_wish_is_one_the_game_master_keeps() -> None:
    simulation = _document()["simulation_state"]
    assert direction.note_preference(simulation, "danger", "more").changes == [c.PreferenceNoted(kind="danger", value="more")]
    assert direction.note_preference(simulation, "danger", "lots").refused
    assert direction.note_preference(simulation, "weather", "sunny").refused
    known = next(iter(simulation["hero_knowledge"]["entries"]))
    assert not direction.note_preference(simulation, "focus", f"entry:{known}").refused
    assert direction.note_preference(simulation, "focus", "entry:npc:nobody").refused


def test_a_stall_asks_the_game_master_once_each_stretch_not_every_turn() -> None:
    """A 60-turn timed autoplay (EV-10's harness, a model that could not move the hero) asked the game master on 53
    turns: once a stall passed STALL_TURNS, every turn after it asked again."""
    from app.apps.rpg.narration.game_master.direction_call import trigger

    document = _document()
    start = int(document["state"].get("turn_count") or 0)
    asked = []
    for turn in range(start + 1, start + 3 * direction.STALL_TURNS + 1):
        document["state"]["turn_count"] = turn
        if trigger({"turn_pipeline": {"changes": []}}, document):
            asked.append(turn - start)
    assert asked == [direction.STALL_TURNS, 2 * direction.STALL_TURNS, 3 * direction.STALL_TURNS]


def test_the_areas_ahead_are_queued_at_launch_neighbours_first(monkeypatch) -> None:
    """EV-10's timed gate: an area queued behind the game master's direction, or only after the first turn, was not
    filled by the hero's arrival. At launch the starting area and its neighbours are queued, the neighbours (where
    the hero may go) ahead of the area the hero stands in, and both ahead of the direction."""
    from app.apps.rpg.narration.game_master.area_call import open_areas
    from app.apps.rpg.session.jobs import game_master_job as job

    document = _document()
    asked: list[tuple[str, int]] = []
    monkeypatch.setattr(job, "enqueue_game_master",
                        lambda session_id, revision, why, **kwargs: asked.append((why, kwargs.get("priority", 5))))
    monkeypatch.setattr("app.apps.rpg.session.persistence.session_records.load_session_from_postgres",
                        lambda session_id: document)
    job.fill_areas_at_launch("rpg_session")
    areas = open_areas(document)
    assert [why for why, _ in asked] == [f"fill:{area}" for area in areas] and areas
    here = job._here_area(document)
    assert all(priority == (job.AREA_HERE_PRIORITY if why == f"fill:{here}" else job.AREA_PRIORITY)
               for why, priority in asked)
    assert job.DIRECTION_PRIORITY < job.AREA_HERE_PRIORITY < job.AREA_PRIORITY
