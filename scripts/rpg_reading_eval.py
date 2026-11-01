"""EV-9's slot set and EV-3's step set: what the intent call reads in a line (evolution roadmap EV-9, EV-3).

Each line is read in its scene by the intent call alone (``session/turn/intent.read_with_model``; no turn is played):
the reading planned, with its slots checked against the scene and the rules as a turn would have them. The scenes are
the intent corpus's (``resources/benchmarks/rpg/intent_corpus/catalog.json``), brought about with the scripted model;
two more states: a companion with the hero (``party``: Liora joins at the grove, for orders) and a level's choice
waiting (``level``). The readings go to RPG's route (``--model``, ``--effort``).

- **Slots** (``resources/benchmarks/rpg/slot_set/slots.jsonl``): each line names the reading expected (its family, and
  the slot's value: how many, how long or until when, the seller, a level's choice, a companion's order, the thing
  given and to whom, the check, a topic asked about). Each kind read right: Wilson lower bound ≥ 0.95.
- **Steps** (``resources/benchmarks/rpg/step_set/steps.jsonl``): each line addresses a quest step a person here holds,
  or none. Precision over the steps the reading names (and the scene accepts): ≥ 0.98; recall over the lines that
  address one: ≥ 0.90.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_reading_eval.py --set slots --model haiku --effort low --allow-database <db> \\
        --output docs/measurements/rpg-slot-set-<date>.json
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests.rehearsal.rpg import worlds  # noqa: E402

SETS = {"slots": ROOT / "resources/benchmarks/rpg/slot_set/slots.jsonl",
        "steps": ROOT / "resources/benchmarks/rpg/step_set/steps.jsonl"}
CATALOG = ROOT / "resources/benchmarks/rpg/intent_corpus/catalog.json"
KIT = {"vesper-9": ("Iron Dagger", "Travel Cloak", "10 silver")}  # as the intent corpus has the hero there
JOIN = "Liora Fen, will you travel with me? Join me."


def wilson(successes: int, n: int, z: float = 1.96) -> dict[str, Any]:
    if not n:
        return {"successes": 0, "n": 0, "rate": None, "lower": None, "upper": None}
    p = successes / n
    centre, spread = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {"successes": successes, "n": n, "rate": round(p, 4), "lower": round((centre - spread) / (1 + z * z / n), 4),
            "upper": round((centre + spread) / (1 + z * z / n), 4)}


def scenes(needed: set[tuple[str, str, str]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Each (world, scene, state) brought about with the scripted model: its stored campaign."""
    from app.apps.rpg.foundation import provider_access
    from app.apps.rpg.foundation.state import access as sections

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    model = worlds.install_scripted_model()
    setattr(provider_access, "rpg_llm_route", lambda: None)  # the scenes are brought about off the route
    client = worlds.turn_client()
    documents: dict[tuple[str, str, str], dict[str, Any]] = {}
    for world, scene, state in sorted(needed):
        session_id = worlds.launch(world, starter_gear=KIT.get(world, ()))
        model.session_id = session_id
        spec = catalog["worlds"][world]["scenes"][scene]
        for command in ["look around", *(spec.get("setup") or []), *([JOIN] if state == "party" else [])]:
            client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
        document = copy.deepcopy(worlds.load(session_id))
        if state == "level":  # a level's choice waiting, in memory only: the reading's choice is checked against it
            sections.player_state_of(sections.simulation_state_of(document))["level_choices_pending"] = 1
        documents[(world, scene, state)] = document
    return documents


def read(document: dict[str, Any], text: str) -> Any:
    from app.apps.rpg.foundation.state import access as sections
    from app.apps.rpg.session.turn.intent import read_with_model
    from app.apps.rpg.session.turn.run import known_abilities
    from app.apps.rpg.session.turn.scene import scene_view

    simulation = sections.simulation_state_of(document)
    abilities = tuple((str(row.get("ability_id")), str(row.get("name"))) for row in known_abilities(document))
    scene = scene_view(simulation, sections.runtime_state_of(document), abilities)
    decided = read_with_model(document, scene, text)
    return decided.reading or (decided.between[0] if decided.between else None), decided


def slot_right(item: dict[str, Any], reading: Any) -> bool:
    expect = item["expect"]
    if reading is None or reading.family != expect["family"]:
        return False
    slots = reading.slots
    kind = item["slot"]
    if kind == "quantity":
        return slots.quantity == expect["quantity"]
    if kind == "wait":
        return (slots.wait_minutes == expect["wait_minutes"]) if "wait_minutes" in expect \
            else slots.until_hour == expect["until_hour"]
    if kind == "seller":
        return reading.second_target_id == expect["second_target_id"]
    if kind == "choice":
        return slots.choice == expect["choice"]
    if kind == "order":
        return reading.target_id == expect["target_id"] and slots.order == expect["order"]
    if kind == "give":
        return reading.target_id == expect["target_id"] and reading.second_target_id == expect["second_target_id"]
    if kind == "check":
        return reading.reason == f"check:{expect['check']}"
    if kind == "topics":
        return expect["topic"] in slots.topics
    raise ValueError(kind)


def run(set_name: str, model: str, effort: str, limit: int) -> dict[str, Any]:
    items = [json.loads(line) for line in SETS[set_name].read_text(encoding="utf-8").splitlines() if line.strip()]
    items = items[:limit] if limit else items
    # The route's model is made once, before the scripted one takes its place for the scenes; then it reads the lines.
    from app.apps.rpg.foundation import provider_access
    from app.providers import service as provider_service

    counter = worlds.install_counting_provider(model=model, effort=effort)
    route = provider_access.rpg_llm_route()
    documents = scenes({(row["world"], row["scene"], row.get("state") or "") for row in items})
    setattr(provider_access, "rpg_llm_route", lambda: route)
    setattr(provider_service, "get_provider", lambda *args, **kwargs: counter)
    rows = []
    for index, item in enumerate(items, 1):
        started = time.perf_counter()
        reading, decided = read(documents[(item["world"], item["scene"], item.get("state") or "")], item["input"])
        row = {"id": item["id"], "input": item["input"], "ms": round((time.perf_counter() - started) * 1000, 1),
               "unavailable": decided.unavailable,
               "reading": None if reading is None else {
                   "family": reading.family, "target_id": reading.target_id,
                   "second_target_id": reading.second_target_id, "reason": reading.reason,
                   "slots": reading.slots.model_dump(mode="json", exclude_defaults=True)},
               "question": decided.question}
        if set_name == "slots":
            row.update(slot=item["slot"], expect=item["expect"], right=slot_right(item, reading))
        else:
            named = (reading.slots.step or None) if reading is not None else None
            row.update(step=item["step"], read_step=named, person=item["person"])
        rows.append(row)
        if index % 50 == 0:
            print(f"{index}/{len(items)}", flush=True)
    return {"rows": rows, "model_calls": len(counter.calls), "provider": worlds.provider_identity(counter)}


def report(set_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    unavailable = sum(row["unavailable"] for row in rows)
    if set_name == "slots":
        by_kind = {kind: wilson(sum(row["right"] for row in rows if row["slot"] == kind),
                                sum(1 for row in rows if row["slot"] == kind))
                   for kind in sorted({row["slot"] for row in rows})}
        return {"by_kind": by_kind, "unavailable": unavailable,
                "passed": all(stats["lower"] is not None and stats["lower"] >= 0.95 for stats in by_kind.values())
                and not unavailable}
    named = [row for row in rows if row["read_step"]]
    addressing = [row for row in rows if row["step"]]
    precision = wilson(sum(row["read_step"] == row["step"] for row in named), len(named))
    recall = wilson(sum(row["read_step"] == row["step"] for row in addressing), len(addressing))
    return {"precision": precision, "recall": recall, "addressing": len(addressing),
            "addressing_none": len(rows) - len(addressing), "unavailable": unavailable,
            "passed": bool(named) and precision["rate"] >= 0.98 and recall["rate"] is not None
            and recall["rate"] >= 0.90 and not unavailable}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--set", choices=sorted(SETS), required=True)
    parser.add_argument("--model", default="haiku")
    parser.add_argument("--effort", default="low", choices=("", "low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    os.environ["OMNIX_RPG_TURNS_PER_HOUR"] = "0"
    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    started = time.perf_counter()
    played = run(args.set, args.model, args.effort, args.limit)
    summary = report(args.set, played["rows"])
    result = {"schema_version": 1, "measurement": f"RPG reading: the {args.set} set", "measured_on": date.today().isoformat(),
              "set": str(SETS[args.set].relative_to(ROOT)), "provider": played["provider"],
              "model_calls": played["model_calls"], "elapsed_s": round(time.perf_counter() - started, 1), **summary,
              "failed": [row for row in played["rows"] if (row.get("right") is False) or
                         (args.set == "steps" and row["read_step"] != row["step"])],
              "rows": played["rows"]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8",
                               newline="\n")
    print(json.dumps({key: summary[key] for key in summary if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
