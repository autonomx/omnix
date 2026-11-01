"""EV-0 part 1's gate: what the game master's panel tells the player (evolution roadmap EV-0, owner question 12).

The frozen question set (``resources/benchmarks/rpg/game_master_panel/questions.jsonl``: 150 questions, 30 at each
of five points) is asked of an Aurelia campaign through the panel's own route (``POST
/api/rpg/sessions/{id}/game-master``). The campaign is played to each point with the scripted model (the arrival grove,
Starfall Village with Orik met, the Wayfarers' Guild after asking for work, Skybridge Pass after a fight, Valecourt
with Hollis met); the questions go to RPG's route (``--model``, ``--effort``: the Claude CLI).

Each answer shown (one withheld by the panel's own check tells nothing) is checked for telling what the hero must not
learn yet: a secret of the world's people, an entry the hero has not met (a person, place, group, thing, creature,
quest), a hidden place, a fact the hero has not been told, or the game master's plans (a beat not reached):

- by code: it names a secret (``names_a_secret``) or holds most of the words of one or of an unlearned fact, or names
  an unmet entry or a hidden place;
- by a judge (a call that sees the secrets, the unmet entries, the facts and the plans; it runs only here, never in
  play, as question 14 allows for the consistency check), on every answer shown.

A question also changes nothing: the stored campaign (its revision and its document, hashed) is the same after it.

The target (roadmap §6): no answer tells any of it, with the upper bound reported (Wilson 95%).

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_panel_eval.py --model sonnet --effort low --allow-database <db> \\
        --output docs/measurements/rpg-game-master-panel-<date>.json
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import math
import os
import re
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests.rehearsal.rpg import worlds  # noqa: E402

QUESTIONS = ROOT / "resources/benchmarks/rpg/game_master_panel/questions.jsonl"
# The commands that bring the campaign to each point, played with the scripted model.
POINTS: dict[str, tuple[str, ...]] = {
    "grove": ("look around", "talk to Liora Fen"),
    "village": ("go to Starfall Village", "talk to Orik Stonewake", "ask Orik Stonewake about work",
                "talk to Brindle Gearwing"),
    "guild": ("go to the Wayfarers' Guild", "talk to Miri Kestrel", "ask Miri Kestrel about work"),
    "pass": ("go to Starfall Village", "go to Skybridge Pass", "attack the echo wolf", "attack the echo wolf",
             "attack the echo wolf", "attack the echo wolf"),
    "valecourt": ("go to Starfall Village", "go to Valecourt", "look around", "talk to Hollis Brask"),
}
SHARE = 0.6  # of a secret's (or an unlearned fact's) words an answer holding them tells it
JUDGE_PROMPT = """You check what a game master told a player. The player's hero knows, or has been shown (this the
game master may tell, in any words):
KNOWN: {known}

The player's hero must not learn, yet:
SECRETS (of the world's people): {secrets}
UNMET (people, places, groups, things, creatures and quests the hero has not met or heard of): {unmet}
UNLEARNED (facts the hero has not been told): {facts}
PLANS (what the game master has not played yet): {plans}

The player asked: {question}
The game master answered: {answer}

Does the answer tell the player any SECRET, describe any UNMET entry beyond naming what the player named, state any
UNLEARNED fact, or reveal any PLAN, beyond what KNOWN holds? What KNOWN holds is fine to tell, even when it shares a
name or some words with an item above (a place and a group can share a name); hints a game master gives at a table are
fine; saying it cannot tell is fine. Reply with JSON only: {{"reveals": true or false, "what": "the item revealed, or empty"}}"""
_WORD = re.compile(r"[a-z][a-z'-]{3,}")
_COMMON = frozenset("that this with from have been were they them their there what when where which while will would "
                    "could should about into than then also only once even ever very some most more much many".split())


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _words(text: str) -> set[str]:
    """A text's words that carry meaning, a plural as its singular ("dreams" is "dream")."""
    return {word[:-1] if word.endswith("s") and len(word) > 4 else word
            for word in _WORD.findall(text.casefold()) if word not in _COMMON}


def _holds(answer: str, text: str, *, asked: str = "") -> bool:
    """Whether ``answer`` holds most of ``text``'s words (a secret or a fact told in other words), not counting the
    words the player used themselves (echoing "why does she dream of cities?" tells nothing)."""
    words = _words(text) - _words(asked)
    return len(words) >= 2 and len(words & _words(answer)) / len(words) >= SHARE


def wilson_upper(successes: int, n: int, z: float = 1.96) -> float | None:
    if not n:
        return None
    p = successes / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((centre + spread) / (1 + z * z / n), 4)


def kept_from_hero(document: dict[str, Any]) -> dict[str, Any]:
    """What the hero must not learn yet, at this point of the campaign."""
    from app.apps.rpg.foundation.state import access as sections
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries
    from app.apps.rpg.rules.routines import goals, next_beat

    simulation = _d(sections.simulation_state_of(document))
    world = _d(sections.world_model_of(simulation))
    known = known_entries(simulation)
    told_ids = {str(fact_id) for ids in _d(_d(simulation.get("dialogue")).get("known_facts")).values() for fact_id in ids}
    unmet = {entry_id: str(row.get("name") or row.get("title") or "") for entry_id, row in world_entries(simulation).items()
             if entry_id not in known}
    hidden = [str(_d(row).get("name") or "") for row in _d(world.get("locations")).values()
              if _d(row).get("hidden") is True]
    facts = [str(_d(fact).get("text") or "") for row in world.get("knowledge") or ()
             for fact in _d(row).get("facts") or () if str(_d(fact).get("fact_id") or "") not in told_ids]
    plans = [f"{_d(world.get('npcs')).get(npc_id, {}).get('name', npc_id)}: {next_beat(simulation, npc_id, goal).get('summary') or next_beat(simulation, npc_id, goal).get('id')}"
             for npc_id, goal in goals(simulation) if next_beat(simulation, npc_id, goal)]
    from app.apps.rpg.narration.game_master.panel import known_view

    shown = json.dumps(known_view(document), ensure_ascii=False)
    # What the hero has been shown is theirs to hear (a quest's "Reach Starfall Village", a met person's description),
    # as the panel's own check has it; a name or a fact only in that sense is no leak.
    unmet = {entry_id: name for entry_id, name in unmet.items() if name.casefold() not in shown.casefold()}
    hidden = [name for name in hidden if name.casefold() not in shown.casefold()]
    facts = [fact for fact in facts if not _holds(shown, fact)]
    return {"shown": shown, "secrets": [str(text) for text in secrets_held(world.get("npcs"))], "unmet": unmet, "hidden": [name for name in hidden if name], "facts": [fact for fact in facts if fact],
            "plans": plans}


def _secret_texts(kept: dict[str, Any]) -> list[str]:
    return list(kept["secrets"])


def code_check(answer: str, kept: dict[str, Any], world_npcs: dict[str, Any], question: str) -> list[str]:
    """What code finds an answer tells that it must not (the panel's own check is the first of these)."""
    from app.apps.rpg.rules.contracts import secrets_held
    from app.apps.rpg.rules.secrets import names_a_secret

    found = []
    if names_a_secret(answer, list(secrets_held(world_npcs))):
        found.append("names a secret")
    found += [f"secret: {text}" for text in _secret_texts(kept) if _holds(answer, text, asked=question)]
    found += [f"fact: {text}" for text in kept["facts"] if _holds(answer, text, asked=question)]
    asked = question.casefold()
    for name in [*kept["unmet"].values(), *kept["hidden"]]:
        # An unmet name the player used themselves is theirs to say back; one the answer brings in is told.
        if len(name) > 3 and re.search(rf"(?<![\w']){re.escape(name.casefold())}(?![\w'])", answer.casefold()) \
                and name.casefold() not in asked:
            found.append(f"names: {name}")
    return found


def judge(provider: Any, kept: dict[str, Any], question: str, answer: str) -> dict[str, Any]:
    from app.providers.base import ChatMessage

    prompt = JUDGE_PROMPT.format(
        known=kept["shown"], secrets=json.dumps(_secret_texts(kept), ensure_ascii=False),
        unmet=json.dumps(sorted({*kept["unmet"].values(), *kept["hidden"]} - {""}), ensure_ascii=False),
        facts=json.dumps(kept["facts"], ensure_ascii=False), plans=json.dumps(kept["plans"], ensure_ascii=False),
        question=json.dumps(question), answer=json.dumps(answer, ensure_ascii=False))
    try:
        raw = str(getattr(provider.chat_completion([ChatMessage(role="user", content=prompt)], stream=False),
                          "content", "") or "")
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        verdict = json.loads(match.group(0)) if match else {}
    except Exception as exc:  # a judge that fails is reported, not counted as clean
        return {"reveals": None, "what": f"judge failed: {type(exc).__name__}"}
    return {"reveals": verdict.get("reveals") is True, "what": str(verdict.get("what") or "")}


def _stored(session_id: str) -> tuple[int, str]:
    from app.apps.rpg.session.persistence.session_records import (
        load_session_from_postgres,
        load_session_version_from_postgres,
    )

    document = load_session_from_postgres(session_id) or {}
    text = json.dumps(document, sort_keys=True, default=str)
    return int((load_session_version_from_postgres(session_id) or (0,))[0]), hashlib.sha256(text.encode()).hexdigest()


def run(model: str, effort: str, *, scripted_only: bool = False) -> dict[str, Any]:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.apps.rpg.edge.api.feature_routes.rpg_game_master_routes import register_rpg_game_master_routes
    from app.apps.rpg.foundation.state import access as sections
    from tests.support.routers import include_router_registrar

    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    from app.apps.rpg.foundation import provider_access
    from app.providers import service as provider_service

    # The route's model, made once; then each phase points RPG's provider at its own: the turns to a point at the
    # scripted model (no route), the questions at the route's model.
    provider = None if scripted_only else worlds.install_counting_provider(model=model, effort=effort)
    route = provider_access.rpg_llm_route() if provider is not None else None
    scripted = worlds.install_scripted_model()

    def use(model_for_phase: Any, phase_route: Any) -> None:
        setattr(provider_access, "rpg_llm_route", lambda: phase_route)
        setattr(provider_service, "get_provider", lambda *args, **kwargs: model_for_phase)

    session_id = worlds.launch("aurelia")
    turns = worlds.turn_client()
    app = FastAPI()
    include_router_registrar(app, register_rpg_game_master_routes)
    panel = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "rpg-panel-eval"})
    rows: list[dict[str, Any]] = []
    for point, commands in POINTS.items():
        use(scripted, None)  # the turns to the point: the scripted model reads them
        scripted.session_id = session_id
        played = []
        for command in commands:
            for _ in range(12):  # a fight still on is fought to its end before the road is taken
                fighting = _d(_d(worlds.load(session_id).get("simulation_state")).get("combat_state")).get("active")
                if fighting is not True or command.startswith("attack"):
                    break
                played.append(turns.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": "attack"}).status_code)
            played.append(turns.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command}).status_code)
        if provider is not None:  # the questions: the route's model (scripted: the harness's own check, no model)
            use(provider, route)
        document = worlds.load(session_id)
        kept = kept_from_hero(document)
        at = str(_d(sections.simulation_state_of(document)).get("current_location_id") or "")
        npcs = _d(sections.world_model_of(_d(sections.simulation_state_of(document))).get("npcs"))
        for item in (row for row in questions if row["point"] == point):
            before = _stored(session_id)
            started = time.perf_counter()
            response = panel.post(f"/api/rpg/sessions/{session_id}/game-master", json={"question": item["question"]})
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            entry = _d(response.json().get("entry")) if response.status_code == 200 else {}
            answer, withheld = str(entry.get("answer") or ""), entry.get("withheld") is True
            found = [] if withheld or not answer else code_check(answer, kept, npcs, item["question"])
            verdict = {"reveals": False, "what": ""} if withheld or not answer else judge(
                provider.inner if hasattr(provider, "inner") else provider, kept, item["question"], answer)
            rows.append({**item, "http": response.status_code, "ms": elapsed, "answer": answer, "withheld": withheld,
                         "code": found, "judge": verdict, "changed": _stored(session_id) != before,
                         "at": at, "turns_to_point": played})
    return {"session_id": session_id, "rows": rows}


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    asked = len(rows)
    shown = [row for row in rows if not row["withheld"] and row["answer"]]
    code = [row for row in rows if row["code"]]
    judged = [row for row in rows if row["judge"]["reveals"] is True]
    leaks = {row["id"] for row in [*code, *judged]}
    by = {}
    for category in sorted({row["category"] for row in rows}):
        group = [row for row in rows if row["category"] == category]
        by[category] = {"asked": len(group), "withheld": sum(row["withheld"] for row in group),
                        "leaks": sum(row["id"] in leaks for row in group)}
    return {
        "asked": asked, "answered": sum(row["http"] == 200 for row in rows), "shown": len(shown),
        "withheld": sum(row["withheld"] for row in rows),
        "leaks": {"by_code": len(code), "by_judge": len(judged), "either": len(leaks),
                  "upper_95": wilson_upper(len(leaks), asked)},
        "judge_failed": sum(row["judge"]["reveals"] is None for row in rows),
        "changed_the_campaign": sum(row["changed"] for row in rows),
        "by_category": by,
        "leaked": [{key: row[key] for key in ("id", "point", "category", "question", "answer", "code", "judge")}
                   for row in rows if row["id"] in leaks],
        "points": {row["point"]: row["at"] for row in rows},  # where the hero stood when each point's were asked
        "passed": asked >= 150 and not leaks and not any(row["changed"] for row in rows)
        and all(row["http"] == 200 for row in rows) and not any(row["judge"]["reveals"] is None for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--provider", choices=("route", "scripted"), default="route",
                        help="scripted: the harness's own check (the scripted model answers nothing: all withheld)")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--effort", default="low", choices=("", "low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    # The per-user hourly budget counts questions with turns (RQ-8.2); a benchmark's 150 would be refused past it.
    os.environ["OMNIX_RPG_TURNS_PER_HOUR"] = "0"
    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    started = time.perf_counter()
    played = run(args.model, args.effort, scripted_only=args.provider == "scripted")
    summary = report(played["rows"])
    result = {"schema_version": 1, "measurement": "RPG game master panel (EV-0 part 1)",
              "measured_on": date.today().isoformat(), "world": "aurelia", "questions": str(QUESTIONS.relative_to(ROOT)),
              "provider": {"model": args.model, "effort": args.effort}, "elapsed_s": round(time.perf_counter() - started, 1),
              **summary, "rows": played["rows"]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8",
                               newline="\n")
    print(json.dumps({key: summary[key] for key in ("asked", "shown", "withheld", "leaks", "judge_failed",
                                                     "changed_the_campaign", "by_category", "passed")}, indent=2))


if __name__ == "__main__":
    main()
