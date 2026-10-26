"""Measure how the RPG understands player inputs today, on the RQ-0.4 intent corpus.

Each corpus item names a world, a scene (where the player stands), the input, and its labels: action family, target
entity, and whether the correct handling changes campaign state. The harness launches the three worlds on a
disposable PostgreSQL database (``tests/rehearsal/rpg/worlds.py``), brings each scene about by playing its setup
commands, and snapshots it. Then, for every item, it measures today's deterministic understanding, without a model:

1. **Static reading** (``play``): the turn's command grammar on the campaign's scene (``command_reading``,
   RQ-3.1); a reading confident enough to skip the intent call is "resolved without a model". (Before RQ-2.10 it
   replayed the older turn path's matchers, in the order that path ran them; the RQ-0.4 baseline measured those.)
   ``--mode grammar`` reads the corpus scenes from the catalog instead, with no campaign at all.
2. **Play** (``--mode play``, the default): the scene's snapshot is restored, the input is played through
   ``POST /api/rpg/sessions/{id}/turn`` with the scripted model (the intent router answers "{}", so the engine
   decides; ``--provider route`` sends the intent call to RPG's settings route, the Claude CLI here, and keeps
   the narration deterministic), and the saved game is compared with the snapshot. A material change (place, purse, pack, equipment,
   party, quests, skills, hit points or a fight, an NPC's health, fatigue relieved) makes the turn stateful, and
   decides the family and target (a changed place is a move, a smaller purse a purchase, ...). Without one, the
   reading the turn ran on stands (the grammar's, or the intent call's when the grammar left it to the model; a
   question back is a clarification) and the turn is not stateful. Time passing and needs drifting are not
   material.

Metrics, each with its own denominator and Wilson 95% bounds: action family accuracy (all items), target entity
accuracy (items with a gold target; the prediction is resolved to a catalog entity by id, alias id or name), and the
false stateful rate (items whose correct handling changes nothing, but the turn changed state). Missed stateful
(stateful items that changed nothing) and the share of inputs the game resolves without a model call are reported
alongside. ``--model-advisory`` is not implemented for the baseline: the deterministic reading is the baseline.

The held-out file is frozen: its SHA-256 is pinned below and the harness refuses to run when it differs.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_intent_eval.py --split held_out --output docs/measurements/rpg-intent-baseline-<date>.json
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests.rehearsal.rpg.stats import proportion  # noqa: E402

CORPUS = ROOT / "resources/benchmarks/rpg/intent_corpus"
HELD_OUT = CORPUS / "held_out.jsonl"
# Frozen 2026-10-23 (RQ-0.4). Changing the held-out set is a re-freeze: change this pin in a reviewed commit.
HELD_OUT_SHA256 = "80fec6faa4b5ff71f6e7505bfd3f345a17e91526b8a9b302647eb104b5217811"
STATEFUL_FAMILIES = {"move", "buy", "sell", "attack", "take", "drop", "give", "use_item", "equip", "unequip", "rest",
                     "quest", "practice", "party"}


def held_out_digest() -> str:
    """The held-out file's SHA-256, over LF line endings (a Windows checkout may write CRLF)."""
    return hashlib.sha256(HELD_OUT.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_frozen_held_out() -> None:
    digest = held_out_digest()
    if digest != HELD_OUT_SHA256:
        raise SystemExit(f"the frozen held-out set changed: sha256 {digest}, pinned {HELD_OUT_SHA256}")


def load_items(split: str) -> list[dict[str, Any]]:
    names = {"held_out": ["held_out"], "dev": ["dev"], "all": ["dev", "held_out"]}[split]
    rows = []
    for name in names:
        with (CORPUS / f"{name}.jsonl").open(encoding="utf-8") as stream:
            rows.extend(json.loads(line) for line in stream if line.strip())
    return rows


# --- entity resolution -----------------------------------------------------------------------------------------

def _norm(text: Any) -> str:
    value = re.sub(r"[^a-z0-9:' -]+", " ", str(text or "").lower())
    value = re.sub(r"\b(the|a|an|my|some|of|for)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class Catalog:
    """A world's entities, by id, by the ids the engine may report, and by the names the player uses."""

    def __init__(self, world: dict[str, Any]) -> None:
        self.entities = world["entities"]
        self.scenes = world["scenes"]
        self.by_id: dict[str, str] = {}
        self.by_name: list[tuple[str, str]] = []
        for key, entity in self.entities.items():
            self.by_id[key.lower()] = key
            for alias in entity.get("alias_ids") or ():
                self.by_id[str(alias).lower()] = key
            for name in entity.get("names") or ():
                if _norm(name):
                    self.by_name.append((_norm(name), key))
        self.by_name.sort(key=lambda pair: -len(pair[0]))

    def same_target(self, predicted: str | None, label: str) -> bool:
        """The labelled entity, or for an offer the thing it sells (buying "a torch" is buying the torch on offer)."""
        if predicted == label:
            return True
        offer, thing = self.entities.get(label) or {}, self.entities.get(predicted or "") or {}
        if offer.get("kind") != "offer" or thing.get("kind") != "item":
            return False
        sold = [_norm(name) for name in offer.get("names") or ()]
        return any(re.search(rf"(?<![a-z0-9]){re.escape(_norm(name))}(?![a-z0-9])", text)
                   for name in thing.get("names") or () if _norm(name) for text in sold)

    def resolve(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.lower() in self.by_id:
            return self.by_id[text.lower()]
        # An engine id built from a canon slug ("npc:liora-fen:..." or "creature:echo-wolf").
        for prefix in sorted(self.by_id, key=len, reverse=True):
            if ":" in prefix and text.lower().startswith(prefix + ":"):
                return self.by_id[prefix]
        # An id the catalog does not list is named by its last part ("location:market-road:northern-road" is the
        # northern road, not "the market" its region's slug happens to spell).
        named = text.rsplit(":", 1)[-1] if ":" in text else text
        normalized = _norm(named.replace("_", " ").replace("-", " "))
        for name, key in self.by_name:
            if name == normalized:
                return key
        for name, key in self.by_name:
            if len(name) > 3 and re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", normalized):
                return key
        return None


# --- the turn's own reading ----------------------------------------------------------------------------------


def static_reading(simulation_state: dict[str, Any], runtime_state: dict[str, Any], text: str) -> dict[str, Any]:
    """What the turn's command grammar makes of the input in the campaign's scene, without a model (RQ-3.1)."""
    from app.apps.rpg.session.command_reading import read_command, skip_reason

    reading = read_command(copy.deepcopy(simulation_state), text, copy.deepcopy(runtime_state))
    return {"family": reading.family, "target_ref": reading.target_id or None, "stateful": reading.stateful,
            "source": f"grammar:{reading.reason}", "gate": bool(skip_reason(reading))}


# --- material state -------------------------------------------------------------------------------------------

def _copper(currency: Any) -> int:
    currency = currency if isinstance(currency, dict) else {}
    return int(currency.get("gold") or 0) * 100 + int(currency.get("silver") or 0) * 10 + int(currency.get("copper") or 0)


def material_state(session: dict[str, Any]) -> dict[str, Any]:
    from app.apps.rpg.rules.combat.runtime_core import get_combat_state

    sim = copy.deepcopy(session.get("simulation_state") or {})
    player = sim.get("player_state") or {}
    inventory = player.get("inventory_state") or {}
    items: Counter = Counter()
    for item in inventory.get("items") or ():
        items[str(item.get("item_id") or item.get("name"))] += int(item.get("qty") or item.get("quantity") or 1)
    equipment = {**((player.get("inventory") or {}).get("equipment") or {}), **(inventory.get("equipment") or {})}
    return {
        "location": str(player.get("location_id") or sim.get("location_id") or ""),
        "purse": _copper(player.get("currency") or inventory.get("currency")),
        "items": dict(items),
        "equipment": json.dumps(equipment, sort_keys=True),
        "party": sorted(str(companion.get("id") or companion.get("npc_id") or companion.get("name"))
                        for companion in (player.get("party_state") or {}).get("companions") or ()),
        "quests": {str(quest.get("id")): str(quest.get("status")) for quest in (sim.get("quest_state") or {}).get("quests") or ()},
        "skills": {key: [int(value.get("level") or 0), int(value.get("xp") or 0)]
                   for key, value in (player.get("skills") or {}).items() if isinstance(value, dict)},
        "hp": int((((player.get("resources") or {}).get("hp")) or {}).get("current") or 0),
        "combat": get_combat_state(sim).get("active") is True,
        "npc_health": {str(row.get("id")): int(row.get("health") or 100) for row in sim.get("actor_states") or ()
                       if isinstance(row, dict)},
        "fatigue": int((sim.get("survival") or {}).get("fatigue") or 0),
    }


def changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if after["location"] != before["location"]:
        found.append({"kind": "location", "to": after["location"]})
    if after["combat"] and not before["combat"]:
        found.append({"kind": "combat_started"})
    hurt = [key for key, value in after["npc_health"].items() if value < before["npc_health"].get(key, 100)]
    if hurt:
        found.append({"kind": "npc_hurt", "ids": hurt})
    if after["hp"] < before["hp"]:
        found.append({"kind": "player_hurt"})
    joined = [key for key in after["party"] if key not in before["party"]]
    if joined:
        found.append({"kind": "party_joined", "ids": joined})
    if after["party"] != before["party"] and not joined:
        found.append({"kind": "party_changed"})
    # A quest someone now offers (new, "available") is the world's doing, not the hero's: what the hero did to a
    # quest (took it, finished it, failed it) is.
    quests = [key for key, status in after["quests"].items()
              if before["quests"].get(key) != status and not (key not in before["quests"] and status == "available")]
    if quests:
        found.append({"kind": "quest_changed", "ids": quests})
    skills = [key for key, value in after["skills"].items() if value != before["skills"].get(key)]
    if skills:
        found.append({"kind": "skill_changed", "ids": skills})
    if after["purse"] != before["purse"]:
        found.append({"kind": "purse", "delta": after["purse"] - before["purse"]})
    gained = [key for key, qty in after["items"].items() if qty > before["items"].get(key, 0)]
    lost = [key for key, qty in before["items"].items() if qty > after["items"].get(key, 0)]
    if gained:
        found.append({"kind": "items_gained", "ids": gained})
    if lost:
        found.append({"kind": "items_lost", "ids": lost})
    if after["equipment"] != before["equipment"]:
        found.append({"kind": "equipment"})
    if after["fatigue"] < before["fatigue"] or after["hp"] > before["hp"]:
        found.append({"kind": "rested"})
    return found


def observed_reading(found: list[dict[str, Any]], static: dict[str, Any], session: dict[str, Any]) -> dict[str, Any] | None:
    """The family and target the material changes show, or None when nothing material changed."""
    kinds = {change["kind"]: change for change in found}
    if not kinds:
        return None
    service = ((session.get("runtime_state") or {}).get("last_turn_contract") or {}).get("service_result") or {}
    if "location" in kinds:
        return {"family": "move", "target_ref": kinds["location"]["to"]}
    if "combat_started" in kinds or "npc_hurt" in kinds or "player_hurt" in kinds:
        target = (kinds.get("npc_hurt") or {}).get("ids", [None])[0] or static.get("target_ref")
        return {"family": "attack", "target_ref": target}
    if "party_joined" in kinds:
        return {"family": "party", "target_ref": kinds["party_joined"]["ids"][0]}
    if "skill_changed" in kinds and static.get("family") == "practice":
        return {"family": "practice", "target_ref": f"skill:{kinds['skill_changed']['ids'][0]}"}
    purse = kinds.get("purse", {}).get("delta", 0)
    if purse < 0:
        offer = service.get("selected_offer_id") or ((service.get("purchase") or {}).get("offer_id"))
        gained = kinds.get("items_gained", {}).get("ids", [None])[0]
        return {"family": "buy", "target_ref": offer or gained or static.get("target_ref")}
    if purse > 0 and "items_lost" in kinds:
        return {"family": "sell", "target_ref": kinds["items_lost"]["ids"][0]}
    if "items_lost" in kinds:
        family = static["family"] if static.get("family") in {"give", "drop", "use_item"} else "drop"
        return {"family": family, "target_ref": kinds["items_lost"]["ids"][0]}
    if "items_gained" in kinds:
        return {"family": "take", "target_ref": kinds["items_gained"]["ids"][0]}
    if "quest_changed" in kinds:
        return {"family": "quest", "target_ref": kinds["quest_changed"]["ids"][0]}
    if "skill_changed" in kinds:
        return {"family": "practice", "target_ref": f"skill:{kinds['skill_changed']['ids'][0]}"}
    if "equipment" in kinds:
        family = static["family"] if static.get("family") in {"equip", "unequip"} else "equip"
        return {"family": family, "target_ref": static.get("target_ref")}
    if purse > 0:
        return {"family": static.get("family") or "quest", "target_ref": static.get("target_ref")}
    if "rested" in kinds:
        return {"family": "rest", "target_ref": None}
    return {"family": static.get("family"), "target_ref": static.get("target_ref")}


# The corpus labels what the pipeline runs as one mechanic apart: inspecting is looking at a thing, and asking and
# declining are talking to someone (session/turn/intent.py FAMILIES has no inspect, ask or decline). Both a label and
# a reading are scored by the mechanic they name; the exact label's rate is reported beside it.
SAME_MECHANIC = {"inspect": "look", "ask": "talk", "decline": "talk"}


def same_family(predicted: Any, label: Any) -> bool:
    return SAME_MECHANIC.get(str(predicted), str(predicted)) == SAME_MECHANIC.get(str(label), str(label))


def turn_reading(ran: dict[str, Any]) -> dict[str, Any]:
    """The family and target of the reading a turn ran on; a question back is a clarification."""
    if ran["mechanic"] == "clarify":
        return {"family": "clarify", "target_ref": None}
    return {"family": ran["family"], "target_ref": ran["target_ref"] or None}


# --- the run ----------------------------------------------------------------------------------------------------

class Worlds:
    """The three worlds on the database, each scene snapshotted, and a way back to a snapshot."""

    def __init__(self, catalog: dict[str, Any], *, play: bool, provider: str = "scripted", model: str = "",
                 effort: str = "") -> None:
        from app.apps.rpg.session.turn import run
        from tests.rehearsal.rpg import worlds as harness

        self.harness = harness
        self.catalog = {world: Catalog(data) for world, data in catalog["worlds"].items()}
        if provider == "route":
            self.model = harness.install_counting_provider(model=model, effort=effort)
        else:
            self.model = harness.install_scripted_model()
        self.ran: list[dict[str, Any]] = []
        planned_turn = run.run_planned_turn

        def recorded(session: Any, *, request: Any, planned: Any, reading: Any, resolution: Any) -> Any:
            # The reading the turn ran on: the grammar's, or the intent call's when the grammar left it to the model.
            self.ran.append({"mechanic": planned.mechanic, "family": reading.family, "target_ref": reading.target_id})
            return planned_turn(session, request=request, planned=planned, reading=reading, resolution=resolution)

        setattr(run, "run_planned_turn", recorded)
        self.client = harness.turn_client()
        self.sessions: dict[str, str] = {}
        self.snapshots: dict[tuple[str, str], dict[str, Any]] = {}
        self.scene_report: dict[str, dict[str, Any]] = {}
        self.play = play

    def turn(self, session_id: str, command: str) -> tuple[int, float]:
        started = time.perf_counter()
        response = self.client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
        return response.status_code, (time.perf_counter() - started) * 1000

    def restore(self, session_id: str, snapshot: dict[str, Any]) -> None:
        from app.apps.rpg.session.service import save_session

        current = self.harness.load(session_id)
        restored = copy.deepcopy(snapshot)
        restored.setdefault("runtime_state", {})["state_revision"] = (current.get("runtime_state") or {}).get("state_revision")
        save_session(restored)

    def prepare(self, world: str) -> None:
        catalog = self.catalog[world]
        session_id = self.harness.launch(world)
        self.sessions[world] = session_id
        status, _ = self.turn(session_id, "look around")
        opening = self.harness.load(session_id)
        for scene, spec in catalog.scenes.items():
            self.restore(session_id, opening)
            statuses = [status] + [self.turn(session_id, command)[0] for command in spec.get("setup") or ()]
            snapshot = self.harness.load(session_id)
            where = material_state(snapshot)["location"]
            reached = catalog.resolve(where) == catalog.resolve(spec["location_id"])
            self.snapshots[(world, scene)] = snapshot
            self.scene_report[f"{world}/{scene}"] = {"reached": reached, "location": where, "http": statuses}

    def evaluate(self, item: dict[str, Any]) -> dict[str, Any]:
        world, scene = item["world"], item["scene"]
        snapshot = self.snapshots[(world, scene)]
        static = static_reading(snapshot.get("simulation_state") or {}, snapshot.get("runtime_state") or {}, item["input"])
        record: dict[str, Any] = {"id": item["id"], "static": static}
        prediction = {"family": static["family"], "target_ref": static["target_ref"], "stateful": static["stateful"]}
        if self.play:
            session_id = self.sessions[world]
            self.restore(session_id, snapshot)
            calls_before = len(self.model.calls)
            self.ran.clear()
            status, elapsed = self.turn(session_id, item["input"])
            after = self.harness.load(session_id)
            found = changes(material_state(snapshot), material_state(after))
            ran = turn_reading(self.ran[-1]) if self.ran else static
            observed = observed_reading(found, ran, after)
            prediction = {"family": (observed or ran)["family"], "target_ref": (observed or ran)["target_ref"],
                          "stateful": observed is not None}
            record.update({"http": status, "turn_ms": round(elapsed, 1), "changes": found, "ran": self.ran[-1:],
                           "model_calls": self.model.calls[calls_before:]})
        prediction["target_entity"] = self.catalog[world].resolve(prediction["target_ref"])
        record["prediction"] = prediction
        record["correct"] = {
            "family": same_family(prediction["family"], item["action_family"]),
            "family_exact": prediction["family"] == item["action_family"],
            "target": self.catalog[world].same_target(prediction["target_entity"], item["target_entity"])
            if item["target_entity"] else None,
            "stateful": prediction["stateful"] == item["stateful"],
        }
        return record


def metrics(items: list[dict[str, Any]], records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    family_ok = sum(records[item["id"]]["correct"]["family"] for item in items)
    exact_ok = sum(records[item["id"]]["correct"].get("family_exact", records[item["id"]]["correct"]["family"])
                   for item in items)
    targeted = [item for item in items if item["target_entity"]]
    target_ok = sum(bool(records[item["id"]]["correct"]["target"]) for item in targeted)
    calm = [item for item in items if not item["stateful"]]
    false_stateful = sum(records[item["id"]]["prediction"]["stateful"] for item in calm)
    stateful = [item for item in items if item["stateful"]]
    missed = sum(not records[item["id"]]["prediction"]["stateful"] for item in stateful)
    gate = sum(records[item["id"]]["static"]["gate"] for item in items)
    return {
        "action_family_accuracy": proportion(family_ok, len(items)),
        "action_family_exact_label": proportion(exact_ok, len(items)),
        "target_entity_accuracy": proportion(target_ok, len(targeted)),
        "false_stateful_rate": proportion(false_stateful, len(calm)),
        "missed_stateful_rate": proportion(missed, len(stateful)),
        "resolved_without_model": proportion(gate, len(items)),
    }


def breakdown(items: list[dict[str, Any]], records: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[str(item[key])].append(item)
    return {name: {"n": len(group), **{metric: value for metric, value in metrics(group, records).items()
                                      if metric != "resolved_without_model"}} for name, group in sorted(groups.items())}


def confusion(items: list[dict[str, Any]], records: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    table: dict[str, Counter] = defaultdict(Counter)
    for item in items:
        table[item["action_family"]][records[item["id"]]["prediction"]["family"]] += 1
    return {gold: dict(predicted.most_common()) for gold, predicted in sorted(table.items())}


def grammar_scene(catalog: dict[str, Any], world: str, scene: str):
    """The corpus scene as the command grammar sees it (RQ-3.1): who and what is here, and what the world knows."""
    from app.apps.rpg.rules.intent.grammar import SceneEntity, SceneView

    entities = catalog["worlds"][world]["entities"]
    spec = catalog["worlds"][world]["scenes"][scene]
    here = (set(spec.get("present") or ()) | set(spec.get("creatures") or ()) | set(spec.get("exits") or ())
            | set(spec.get("offers") or ()))
    return SceneView(tuple(
        SceneEntity(
            entity_id,
            entity["kind"],
            tuple(entity["names"]) + tuple(alias.replace("_", " ") for alias in entity.get("alias_ids") or ()),
            here=entity_id in here or entity["kind"] in {"item", "skill", "quest"},
        )
        for entity_id, entity in entities.items()
    ))


def grammar_records(catalog: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each item read by the command grammar alone: no campaign, no model."""
    from app.apps.rpg.rules.intent.grammar import parse_command

    scenes: dict[tuple[str, str], Any] = {}
    records: dict[str, dict[str, Any]] = {}
    for item in items:
        key = (item["world"], item["scene"])
        scene = scenes.setdefault(key, grammar_scene(catalog, *key))
        candidate = parse_command(item["input"], scene)
        records[item["id"]] = {
            "prediction": {"family": candidate.family, "target": candidate.target_id, "stateful": candidate.stateful,
                           "confidence": candidate.confidence, "reason": candidate.reason},
            "correct": {"family": candidate.family == item["action_family"],
                        "target": candidate.target_id == item["target_entity"]},
            "static": {"source": f"grammar:{candidate.reason}", "gate": candidate.confidence >= 0.75},
        }
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--split", choices=("held_out", "dev", "all"), default="held_out")
    parser.add_argument("--mode", choices=("play", "grammar"), default="play")
    parser.add_argument("--provider", choices=("scripted", "route"), default="scripted",
                        help="who answers the intent call in play: no advice (scripted), or RPG's settings route")
    parser.add_argument("--model", default="", help="the Claude CLI model for --provider route (default: haiku)")
    parser.add_argument("--effort", default="", choices=("", "low", "medium", "high", "xhigh", "max"),
                        help="the Claude CLI effort level for --provider route (default: as configured)")
    parser.add_argument("--limit", type=int, default=0, help="evaluate only the first N items (a smoke run)")
    parser.add_argument("--allow-database", default="", help="a disposable database whose name lacks 'test'/'bench'")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--records", type=Path, help="also write every item's reading (JSONL)")
    args = parser.parse_args(argv)
    require_frozen_held_out()
    catalog = json.loads((CORPUS / "catalog.json").read_text(encoding="utf-8"))
    items = load_items(args.split)
    if args.limit:
        items = items[: args.limit]
    started = time.perf_counter()
    if args.mode == "grammar":
        return _report_grammar(args, catalog, items, started)
    if args.provider == "route":
        os.environ["OMNIX_RPG_NARRATIVE_WRITER_MODE"] = "deterministic"  # the intent call is measured, not the prose
    from tests.rehearsal.rpg import worlds as harness

    database = harness.require_disposable_database(args.allow_database)
    harness.bootstrap()
    runner = Worlds(catalog, play=args.mode == "play", provider=args.provider, model=args.model, effort=args.effort)
    for world in sorted({item["world"] for item in items}):
        runner.prepare(world)
    records: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items, 1):
        records[item["id"]] = runner.evaluate(item)
        if index % 100 == 0:
            print(f"{index}/{len(items)}", file=sys.stderr)
    stateful_turn_ms = [record["turn_ms"] for record in records.values() if "turn_ms" in record]
    report = {
        "schema_version": 1,
        "measurement": ("RPG intent understanding with the intent call (RQ-3, M2)" if args.provider == "route"
                        else "RPG intent understanding without a model (RQ-0.4 baseline)"),
        "measured_on": date.today().isoformat(),
        "revision": subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip(),
        "database": database,
        "split": args.split,
        "mode": args.mode,
        "items": len(items),
        "held_out_sha256": held_out_digest(),
        "labels": "model-labelled, pending the owner's spot check",
        "model": ({**harness.provider_identity(runner.model), "resolved_models": sorted(runner.model.resolved_models)}
                  if args.provider == "route"
                  else "none: the scripted model answers the intent router with no advice; the engine decides"),
        "model_calls": sum(len(record.get("model_calls") or ()) for record in records.values()),
        "scenes": runner.scene_report,
        "metrics": metrics(items, records),
        # A scene the setup commands did not reach is played where the player stayed; its items are shown apart.
        "metrics_reached_scenes_only": metrics(
            [item for item in items if runner.scene_report.get(f"{item['world']}/{item['scene']}", {}).get("reached")],
            records),
        "unreached_scene_items": sum(not runner.scene_report.get(f"{item['world']}/{item['scene']}", {}).get("reached")
                                     for item in items),
        "by_world": breakdown(items, records, "world"),
        "by_family": breakdown(items, records, "action_family"),
        "family_confusion": confusion(items, records),
        "static_sources": dict(Counter(record["static"]["source"].split(":")[0] for record in records.values()).most_common()),
        "turn_ms_p50": sorted(stateful_turn_ms)[len(stateful_turn_ms) // 2] if stateful_turn_ms else None,
        "elapsed_s": round(time.perf_counter() - started, 1),
        "gates": {"M2 (from RQ-3)": "action family lower >= 0.95, target entity lower >= 0.95, false stateful upper <= 0.010"},
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    if args.records:
        args.records.parent.mkdir(parents=True, exist_ok=True)
        by_id = {item["id"]: item for item in items}
        args.records.write_text("".join(json.dumps({**by_id[key], **value}, sort_keys=True, default=str) + "\n"
                                        for key, value in records.items()), encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    return 0


def _report_grammar(args: Any, catalog: dict[str, Any], items: list[dict[str, Any]], started: float) -> int:
    records = grammar_records(catalog, items)
    report = {
        "schema_version": 1,
        "measurement": "RPG intent understanding by the command grammar alone (RQ-3.1)",
        "measured_on": date.today().isoformat(),
        "revision": subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip(),
        "split": args.split,
        "mode": "grammar",
        "items": len(items),
        "held_out_sha256": held_out_digest(),
        "labels": "model-labelled, pending the owner's spot check",
        "note": "the grammar's stateful flag reads the words only (a purchase of something not on sale is not "
                "stateful); whether a turn changes state is the play mode's measure",
        "metrics": metrics(items, records),
        "by_world": breakdown(items, records, "world"),
        "by_family": breakdown(items, records, "action_family"),
        "family_confusion": confusion(items, records),
        "elapsed_s": round(time.perf_counter() - started, 1),
        "gates": {"M2 (from RQ-3)": "action family lower >= 0.95, target entity lower >= 0.95, false stateful upper <= 0.010"},
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(report["metrics"], indent=2))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("OMNIX_RPG_TURNS_PER_HOUR", "0")
    raise SystemExit(main())
