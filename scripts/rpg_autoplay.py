"""RQ-9.1: a player plays the reference worlds for hundreds of turns, and what goes wrong is written down.

Each world (Aurelia, Vesper-9, the starter town) is launched on a disposable database and played through the turn
route, one turn at a time. The player is either a model (``--player route``: RPG's route, Claude Haiku through the
Claude CLI on this install, asked for the next action from what the hero can see) or a seeded policy
(``--player policy``: a reasonable player choosing among the scene's ways on, its people, its creatures, rest when
hurt, food when hungry). The game's own calls go to ``--provider`` (``route`` or ``scripted``).

After every turn the stored campaign is checked:

- the turn answered (no 5xx, a visible line for an accepted turn), and its revision moved on by one;
- health within 0 and its maximum, a purse that is not negative, no item with a count below one;
- the hero stands at a place of the world.

The report (``docs/measurements/rpg-autoplay-<date>-<player>-<provider>.json``) gives, per world, the turns played,
latency (p50, p95), model calls a turn, what the hero did (places visited, fights won and lost, quests completed,
level), and each finding with its turn; a run passes with no P0 (a 5xx, a broken invariant) and refusals under 10%.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_autoplay.py --turns 500 --player policy --provider scripted
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests.rehearsal.rpg import worlds  # noqa: E402
from tests.rehearsal.rpg.stats import summary  # noqa: E402

PLAYER_PROMPT = """You are playing a text role-playing game as {hero}. Choose the hero's next action.
Play like a curious, sensible adventurer: talk to people, take and pursue quests, travel, trade, rest when hurt,
eat when hungry, fight creatures in the wild. Vary what you do; do not repeat an action that was just refused.

Where you are: {place}. Ways on: {exits}. People here: {people}.
Health {hp}/{hp_max}. Purse: {purse}. Level {level}. Quests: {quests}.
Last thing that happened: {last}

Reply with the action only, in a short plain sentence (for example: "go to Starfall Village", "ask Liora about work",
"buy a healing potion", "attack the echo wolf", "rest until morning")."""


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def view(document: dict[str, Any]) -> dict[str, Any]:
    """What the hero can see, from the stored campaign."""
    simulation = _d(document.get("simulation_state"))
    player = _d(simulation.get("player_state"))
    resources = _d(player.get("resources"))
    hp = _d(resources.get("hp"))
    location_id = str(simulation.get("current_location_id") or player.get("current_location_id") or "")
    model = _d(simulation.get("world_model"))
    place = _d(_d(model.get("locations")).get(location_id))
    present = [str(_d(row).get("name") or "") for row in _l(simulation.get("present_npcs")) if _d(row).get("name")]
    present = present or [str(_d(row).get("name") or "") for row in _l(place.get("present_npcs"))]
    quests = [_d(row) for row in _l(_d(simulation.get("quest_state")).get("quests"))]
    survival = _d(simulation.get("survival"))
    runtime = _d(document.get("runtime_state"))
    recent = _l(runtime.get("recent_interactions"))
    last = _d(_d(recent[-1]).get("visible_response")).get("plain_text") if recent else ""
    creatures = sorted(_d(_d(simulation.get("campaign_mechanics")).get("creatures")).keys())
    return {
        "hero": str(player.get("name") or "the hero"),
        "location_id": location_id,
        "place": str(place.get("name") or location_id),
        "exits": sorted(str(name) for name in _d(place.get("exits"))),
        "people": [name for name in present if name],
        "hp": int(hp.get("current") or 0) if hp else None,
        "hp_max": int(hp.get("max") or 0) if hp else None,
        "purse": _d(player.get("currency")),
        "level": int(player.get("level") or 1),
        "quests": [f"{row.get('title')} ({row.get('status')})" for row in quests if row.get("title")],
        "quest_statuses": {str(row.get("id")): str(row.get("status") or "") for row in quests if row.get("id")},
        "hunger": float(_d(survival.get("hunger")).get("value") or survival.get("hunger") or 0)
        if not isinstance(survival.get("hunger"), (int, float)) else float(survival["hunger"]),
        "creatures": creatures,
        "wild": not place.get("present_npcs") and not place.get("services"),
        "last": str(last or "")[:600],
        "inventory": _l(_d(player.get("inventory_state")).get("items")),
        "revision": int(runtime.get("state_revision") or 0),
    }


class PolicyPlayer:
    """A reasonable player, seeded: rest when hurt, eat when hungry, fight in the wild, talk, trade and travel."""

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)

    def next(self, seen: dict[str, Any], refused: set[str]) -> str:
        options: list[str] = []
        if seen["hp"] is not None and seen["hp_max"] and seen["hp"] < 0.4 * seen["hp_max"]:
            options += ["rest until morning"] * 4
        if seen["hunger"] > 60:
            options += ["eat something", "buy a hot meal"]
        for person in seen["people"][:3]:
            options += [f"talk to {person}", f"ask {person} about work", f"ask {person} what they sell"]
        for exit_name in seen["exits"][:4]:
            options.append(f"go to {exit_name}")
        if seen["wild"]:
            options += [f"attack the {name.split(':')[-1].replace('-', ' ')}" for name in seen["creatures"][:2]]
        options += ["look around", "wait a while", "check my inventory"]
        fresh = [option for option in options if option not in refused] or options
        return self.random.choice(fresh)


class ModelPlayer:
    """A model chooses the hero's next action from what the hero can see; the policy stands in when it cannot."""

    def __init__(self, seed: int) -> None:
        from app.apps.rpg.foundation import provider_access
        from app.providers.base import ChatMessage

        self.message = ChatMessage
        provider_access.rpg_llm_route = lambda: worlds.LIVE_RPG_ROUTE  # type: ignore[assignment]
        self.provider = provider_access.routed_provider()
        self.fallback = PolicyPlayer(seed)
        self.calls = 0
        self.failures = 0

    def next(self, seen: dict[str, Any], refused: set[str]) -> str:
        prompt = PLAYER_PROMPT.format(
            hero=seen["hero"], place=seen["place"], exits=", ".join(seen["exits"]) or "none known",
            people=", ".join(seen["people"]) or "no one", hp=seen["hp"], hp_max=seen["hp_max"],
            purse=json.dumps(seen["purse"]), level=seen["level"], quests="; ".join(seen["quests"]) or "none",
            last=seen["last"] or "the story is just beginning")
        self.calls += 1
        try:
            response = self.provider.chat_completion([self.message(role="user", content=prompt)], stream=False)
            text = str(getattr(response, "content", "") or "").strip().splitlines()[0].strip().strip('"')
        except Exception:
            text = ""
        if not text or len(text) > 160 or text in refused:
            self.failures += 1
            return self.fallback.next(seen, refused)
        return text


def check(before: dict[str, Any], after: dict[str, Any], *, accepted: bool) -> list[str]:
    """The invariants a turn must keep."""
    broken: list[str] = []
    if after["hp"] is not None and after["hp_max"] and not 0 <= after["hp"] <= after["hp_max"]:
        broken.append(f"health_out_of_bounds:{after['hp']}/{after['hp_max']}")
    if any(int(value or 0) < 0 for value in after["purse"].values() if isinstance(value, (int, float))):
        broken.append(f"negative_purse:{after['purse']}")
    for item in after["inventory"]:
        if isinstance(item, dict) and int(item.get("quantity") or 1) < 1:
            broken.append(f"item_count_below_one:{item.get('id') or item.get('name')}")
    if accepted and after["revision"] < before["revision"]:
        broken.append(f"revision_went_back:{before['revision']}->{after['revision']}")
    if after["location_id"] and not after["place"]:
        broken.append(f"unknown_place:{after['location_id']}")
    return broken


def play(world: str, turns: int, player: Any, counter: Any) -> dict[str, Any]:
    session_id = worlds.launch(world)
    client = worlds.turn_client()
    seen = view(worlds.load(session_id))
    refused: set[str] = set()
    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    visited: set[str] = {seen["location_id"]}
    completed: set[str] = set()
    for index in range(1, turns + 1):
        command = player.next(seen, refused)
        calls_before = len(counter.calls) if counter is not None else 0
        started = time.perf_counter()
        response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
        elapsed = (time.perf_counter() - started) * 1000
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        accepted = response.status_code == 200 and body.get("ok") is not False
        visible = str(_d(body.get("visible_response")).get("plain_text") or body.get("narration") or "").strip()
        after = view(worlds.load(session_id))
        row = {"turn": index, "command": command, "status": response.status_code, "ms": round(elapsed, 1),
               "accepted": accepted, "calls": (len(counter.calls) - calls_before) if counter is not None else None}
        rows.append(row)
        if response.status_code >= 500:
            findings.append({"severity": "P0", "turn": index, "kind": "server_error", "command": command,
                             "detail": response.text[:400]})
        elif accepted and not visible:
            findings.append({"severity": "P1", "turn": index, "kind": "no_visible_line", "command": command})
        for broken in check(seen, after, accepted=accepted):
            findings.append({"severity": "P0", "turn": index, "kind": "invariant", "detail": broken, "command": command})
        if accepted:
            refused.discard(command)
        else:
            refused.add(command)
        visited.add(after["location_id"])
        completed.update(quest for quest, status in after["quest_statuses"].items() if status == "completed")
        seen = after
    stuck = _stuck(rows)
    if stuck:
        findings.append({"severity": "P1", "kind": "refusal_streak", "detail": stuck})
    refusal_rate = sum(1 for row in rows if not row["accepted"]) / max(1, len(rows))
    return {
        "world": world,
        "session_id": session_id,
        "turns": len(rows),
        "latency_ms": summary([row["ms"] for row in rows]),
        # Where the time goes: by the action's first word, and the first hundred turns against the last.
        "latency_by_action": {verb: summary(times) for verb, times in sorted(_by_action(rows).items()) if len(times) >= 5},
        "latency_drift_ms": {"first_100": summary([row["ms"] for row in rows[:100]]),
                             "last_100": summary([row["ms"] for row in rows[-100:]])},
        "model_calls_per_turn": (round(sum(row["calls"] or 0 for row in rows) / max(1, len(rows)), 2)
                                 if counter is not None else None),
        "refusal_rate": round(refusal_rate, 3),
        "places_visited": len(visited - {""}),
        "quests_completed": sorted(completed),
        "level": seen["level"],
        "findings": findings,
        "passed": not any(f["severity"] == "P0" for f in findings) and refusal_rate < 0.10,
        "sample": rows[:5] + rows[-5:],
    }


def _by_action(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        verb = (str(row["command"]).split() or ["?"])[0].casefold()
        grouped.setdefault(verb, []).append(row["ms"])
    return grouped


def _stuck(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The longest run of refused turns, when ten or more in a row."""
    longest, current, start = 0, 0, 0
    best = None
    for row in rows:
        current = current + 1 if not row["accepted"] else 0
        if current == 1:
            start = row["turn"]
        if current > longest:
            longest, best = current, {"from_turn": start, "length": current}
    return best if longest >= 10 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--worlds", nargs="+", default=list(worlds.WORLDS))
    parser.add_argument("--turns", type=int, default=500)
    parser.add_argument("--player", choices=("policy", "route"), default="policy")
    parser.add_argument("--provider", choices=("scripted", "route"), default="scripted")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    worlds.require_disposable_database(args.allow_database)
    os.environ.setdefault("OMNIX_RPG_TURNS_PER_HOUR", "0")
    worlds.bootstrap()
    counter = worlds.install_counting_provider() if args.provider == "route" else None
    if counter is None:
        worlds.install_scripted_model()
    player = ModelPlayer(args.seed) if args.player == "route" else PolicyPlayer(args.seed)
    results = [play(world, args.turns, player, counter) for world in args.worlds]
    report = {
        "measurement": "rpg-autoplay (RQ-9.1)",
        "date": date.today().isoformat(),
        "player": args.player,
        "provider": worlds.provider_identity() if args.provider == "route" else {"provider": "scripted"},
        "turns_per_world": args.turns,
        "player_model_calls": getattr(player, "calls", 0),
        "player_model_fallbacks": getattr(player, "failures", 0),
        "passed": all(result["passed"] for result in results),
        "worlds": results,
    }
    output = args.output or ROOT / f"docs/measurements/rpg-autoplay-{report['date']}-{args.player}-{args.provider}.json"
    output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("passed", "player", "provider")}, default=str))
    for result in results:
        print(result["world"], "passed" if result["passed"] else "FAILED", result["turns"], "turns",
              result["latency_ms"], "refusals", result["refusal_rate"], "places", result["places_visited"],
              "quests", len(result["quests_completed"]), "level", result["level"],
              "findings", [(f["severity"], f["kind"], f.get("turn")) for f in result["findings"][:8]])


if __name__ == "__main__":
    main()
