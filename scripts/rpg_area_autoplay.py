"""EV-10's gate: areas are filled in by the time the hero arrives (evolution roadmap EV-10).

Aurelia is launched on a disposable database and played through the turn route for ``--turns`` turns by an exploring
player: it stays a few turns in each region it reaches (looking, talking, searching), then takes the shortest way by
the world's roads to a region it has not stood in, searches the wild now and then (``explore``) and rests when hurt; with every region seen, a seeded policy (``rpg_autoplay.PolicyPlayer``) plays on. The game's own calls, the game master's area
calls among them, go to RPG's route (``--provider route``: the Claude CLI; ``--model`` and ``--effort`` as the other
gates take them).

The area calls are jobs (``rpg.game_master``, ``fill:<area>``), queued when the hero arrives somewhere for the areas
next to them; here worker threads (as many as the live job worker's LLM pool runs at once, ``DEFAULT_POOLS``) claim
and run the RPG's jobs as the live job worker does, beside the turns, with
real timing. With ``--wait`` the player waits for every queued job to finish before the next turn, so the results do
not depend on timing (the gate's second run).

An arrival is a turn after which the hero stands in a region (an area) they had not stood in before. It counts as
filled in when the region's detail (``area_detail``) holds entries after that turn: its fill was stored before the
turn began and folded in at its load. The checks:

- at least 95% of arrivals filled in;
- every area's filled-in entries, by kind, within its budget (``rules/budgets.area_budget``);
- every job finished (none failed or left running at the end).

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_area_autoplay.py --provider route --model sonnet --effort low --turns 200 \\
        --allow-database <db> --output docs/measurements/rpg-area-autoplay-<date>.json
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import random
import sys
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from tests.rehearsal.rpg import worlds  # noqa: E402
from tests.rehearsal.rpg.stats import summary  # noqa: E402

FILLED_TARGET = 0.95
EXPLORE_EVERY = 6  # a search of the land, every this many turns in the wild
STAY_TURNS = 5  # the turns spent in a region before heading on: a player's stay (the fill's lead time, EV-10)
LOCAL = ("look around", "explore the area", "wait a while")


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class Worker:
    """Claims the RPG's queued jobs and runs each by its handler, as the job worker does."""

    def __init__(self) -> None:
        from app.jobs.models import ResourceClass
        from app.jobs.store import default_job_store
        from app.runtime.feature_catalog import load_feature

        self.store = default_job_store()
        self.handlers = {spec.type: spec.handler for spec in load_feature("rpg").job_handlers}
        self.classes = sorted({spec.resource_class for spec in load_feature("rpg").job_handlers}, key=str)
        self.resource = ResourceClass
        self.ran: list[dict[str, Any]] = []
        self.session_id = ""  # the run's campaign: another's job (one left on the database) is not run
        self.stop = threading.Event()
        from app.composition.worker_runtime.pools import DEFAULT_POOLS, parse_pools

        slots = next((pool.concurrency for pool in parse_pools(DEFAULT_POOLS) if pool.name == "llm"), 1)
        self.threads = [threading.Thread(target=self._loop, name=f"rpg-area-gate-worker-{index}", daemon=True)
                        for index in range(slots)]

    def _claim(self) -> Any:
        from app.jobs.models import ClaimJobRequest

        claimed = self.store.claim_next(ClaimJobRequest(worker_id="worker:rpg-area-gate", resource_classes=self.classes,
                                                        lease_seconds=600))
        return claimed.job if claimed.ok else None

    def run_one(self) -> bool:
        from app.jobs.handlers import JobExecutionContext
        from app.jobs.models import FailJobRequest

        from app.composition.worker_runtime.durable_feature_worker import _LeaseBoundJobStore

        job = self._claim()
        if job is None:
            return False
        handler = self.handlers.get(str(job.type))
        started = time.perf_counter()
        leased = _LeaseBoundJobStore(self.store, job)  # every write under this job's lease, as in the job worker
        try:
            theirs = str(_d(getattr(job, "input_payload", None)).get("session_id") or "")
            if handler is None or (theirs and theirs != self.session_id):
                # another feature's job, or another campaign's left on the database: failed under its lease, not run
                leased.fail_job(job.id, FailJobRequest(code="not_this_run", message=str(job.type), retryable=False))
                status = "not_this_run"
            else:
                done = handler(JobExecutionContext(job_store=leased), job)
                status = str(getattr(getattr(done, "status", ""), "value", getattr(done, "status", "")))
        except Exception as exc:  # a handler or a write that raises: recorded, the run goes on
            status = f"raised:{type(exc).__name__}"
        payload = _d(getattr(job, "input_payload", None))
        self.ran.append({"job_id": str(job.id), "type": str(job.type), "why": str(payload.get("why") or ""),
                         "status": status, "s": round(time.perf_counter() - started, 1)})
        return True

    def final_statuses(self) -> dict[str, str]:
        """Each job run, by its status in the store at the end (a retried job's last attempt)."""
        statuses = {}
        for job_id in dict.fromkeys(row["job_id"] for row in self.ran):
            record = self.store.get_job(job_id)
            status = getattr(record, "status", "missing") if record is not None else "missing"
            statuses[job_id] = str(getattr(status, "value", status))
        return statuses

    def _loop(self) -> None:
        while not self.stop.is_set():
            if not self.run_one():
                self.stop.wait(0.5)

    def drain(self) -> None:
        """Run every queued job now (``--wait``, and at the end of a timed run)."""
        while self.run_one():
            pass


class Explorer:
    """The policy player, heading for regions not yet stood in, and searching the land now and then."""

    def __init__(self, seed: int) -> None:
        from rpg_autoplay import PolicyPlayer

        self.policy = PolicyPlayer(seed)
        self.random = random.Random(seed)
        self.turn = 0
        self.region = ""
        self.stayed = 0

    def next(self, seen: dict[str, Any], refused: set[str], document: dict[str, Any], visited: set[str]) -> str:
        self.turn += 1
        simulation = _d(document.get("simulation_state"))
        if _d(simulation.get("combat_state")).get("active") is True:  # a fight is fought, or broken away from
            losing = bool(seen["hp"] and seen["hp_max"] and seen["hp"] < 0.3 * seen["hp_max"])
            return "I break away and flee." if losing else "attack"
        if seen["hp"] is not None and seen["hp_max"] and seen["hp"] < 0.4 * seen["hp_max"]:
            return "rest until morning"
        places = _d(_d(simulation.get("world_model")).get("locations"))
        names = {str(_d(row).get("name") or ""): str(_d(row).get("region_id") or "") for row in places.values()}
        region = str(_d(places.get(seen["location_id"])).get("region_id") or "")
        self.stayed = self.stayed + 1 if region == self.region else 1
        self.region = region
        if self.stayed <= STAY_TURNS:  # a stay first: what is here, its people, a search
            people = [f"talk to {person}" for person in seen["people"][:2]]
            options = [line for line in (*LOCAL, *people) if line not in refused] or list(LOCAL)
            return self.random.choice(options)
        new = [name for name in seen["exits"] if names.get(name) and names[name] not in visited
               and f"go to {name}" not in refused]
        if new:
            return f"go to {self.random.choice(new)}"
        if seen["wild"] and self.turn % EXPLORE_EVERY == 0 and "explore the area" not in refused:
            return "explore the area"
        step = _toward_new_region(simulation, seen["location_id"], visited)
        if step and f"go to {step}" not in refused:  # the shortest way to a region not yet stood in
            return f"go to {step}"
        return self.policy.next(seen, refused)


def _toward_new_region(simulation: dict[str, Any], here: str, visited: set[str]) -> str:
    """The name of the next place on the shortest way (by the world's roads) to a place in a region not yet stood in."""
    from collections import deque

    world = _d(simulation.get("world_model"))
    places = _d(world.get("locations"))
    roads: dict[str, list[str]] = {}
    for route in world.get("routes") or ():
        start, end = str(_d(route).get("from") or ""), str(_d(route).get("to") or "")
        if start and end:
            roads.setdefault(start, []).append(end)
            roads.setdefault(end, []).append(start)
    first: dict[str, str] = {here: ""}
    queue = deque([here])
    while queue:
        place = queue.popleft()
        region = str(_d(places.get(place)).get("region_id") or "")
        if place != here and region and region not in visited:
            return str(_d(places.get(first[place])).get("name") or "")
        for neighbour in sorted(roads.get(place, ())):
            if neighbour not in first:
                first[neighbour] = first[place] or neighbour
                queue.append(neighbour)
    return ""


def _region(document: dict[str, Any], location_id: str) -> str:
    simulation = _d(document.get("simulation_state"))
    return str(_d(_d(_d(simulation.get("world_model")).get("locations")).get(location_id)).get("region_id") or "")


def _detail(document: dict[str, Any]) -> dict[str, Any]:
    from app.apps.rpg.foundation.state import access as sections

    return _d(sections.area_detail_of(_d(sections.simulation_state_of(document))))


def _within_budgets(document: dict[str, Any]) -> dict[str, Any]:
    """Each filled-in area's entries by kind against its budget."""
    from app.apps.rpg.foundation.state import access as sections
    from app.apps.rpg.rules.budgets import area_budget

    simulation = _d(sections.simulation_state_of(document))
    over: list[str] = []
    counts: dict[str, dict[str, int]] = {}
    for area_id, held in sorted(_detail(document).items()):
        kinds: dict[str, int] = {}
        for entry in _d(held).get("entries") or ():
            kinds[str(_d(entry).get("kind") or "")] = kinds.get(str(_d(entry).get("kind") or ""), 0) + 1
        counts[area_id] = kinds
        budget = area_budget(simulation, area_id)
        over += [f"{area_id}:{kind}:{count}>{budget.get(kind, 0)}" for kind, count in kinds.items()
                 if count > int(budget.get(kind, 0))]
    return {"entries_by_area": counts, "over_budget": over, "passed": not over}


def play(turns: int, seed: int, *, wait: bool) -> dict[str, Any]:
    from rpg_autoplay import view

    worker = Worker()
    session_id = worlds.launch("aurelia")
    worker.session_id = session_id
    if not wait:
        for thread in worker.threads:
            thread.start()
    client = worlds.turn_client()
    document = worlds.load(session_id)
    seen = view(document)
    visited = {_region(document, seen["location_id"])} - {""}
    player = Explorer(seed)
    refused: set[str] = set()
    rows: list[dict[str, Any]] = []
    arrivals: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index in range(1, turns + 1):
        if wait:
            worker.drain()
        command = player.next(seen, refused, document, visited)
        began = time.perf_counter()
        response = client.post(f"/api/rpg/sessions/{session_id}/turn", json={"command": command})
        elapsed = (time.perf_counter() - began) * 1000
        accepted = response.status_code == 200
        document = worlds.load(session_id)
        after = view(document)
        rows.append({"turn": index, "command": command, "status": response.status_code, "ms": round(elapsed, 1)})
        (refused.discard if accepted else refused.add)(command)
        region = _region(document, after["location_id"])
        if region and region not in visited:
            visited.add(region)
            entries = len(_d(_detail(document).get(region)).get("entries") or ())
            arrivals.append({"turn": index, "area": region, "entries": entries, "filled": entries > 0,
                             "at_s": round(time.perf_counter() - started, 1),
                             "fills_finished": sum(1 for job in worker.ran if job["why"] == f"fill:{region}")})
        seen = after
    if not wait:  # the job in hand finishes, then every job still queued is run, so every fill is counted
        worker.stop.set()
        for thread in worker.threads:
            thread.join(timeout=900)
        if any(thread.is_alive() for thread in worker.threads):
            raise SystemExit("the worker's job did not finish in 15 minutes")
    worker.drain()
    filled = sum(1 for row in arrivals if row["filled"])
    fills = [job for job in worker.ran if job["why"].startswith("fill:")]
    statuses = {job_id: status for job_id, status in worker.final_statuses().items()
                if not any(row["job_id"] == job_id and row["status"] == "not_this_run" for row in worker.ran)}
    jobs_ok = bool(statuses) and all(status in {"completed", "succeeded"} for status in statuses.values())
    budgets = _within_budgets(worlds.load(session_id))
    rate = round(filled / len(arrivals), 3) if arrivals else None
    checks = {
        "filled_on_arrival": {"arrivals": len(arrivals), "filled": filled, "rate": rate, "target": FILLED_TARGET,
                              "passed": bool(arrivals) and filled / len(arrivals) >= FILLED_TARGET},
        "within_budgets": budgets,
        "jobs_finished": {"jobs": len(statuses), "attempts": len(worker.ran),
                          "statuses": sorted(set(statuses.values())), "passed": jobs_ok},
    }
    return {
        "session_id": session_id, "turns": len(rows), "wait": wait,
        "turn_ms": summary([row["ms"] for row in rows]),
        "regions_reached": sorted(visited), "arrivals": arrivals,
        "area_fill_s": summary([job["s"] for job in fills]), "area_fills": len(fills),
        "jobs_by_type": {kind: sum(1 for job in worker.ran if job["type"] == kind)
                         for kind in sorted({job["type"] for job in worker.ran})},
        "refusals": sum(1 for row in rows if row["status"] != 200),
        "checks": checks, "passed": all(check["passed"] for check in checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--provider", choices=("scripted", "route"), default="route")
    parser.add_argument("--model", default="", help="the route's model (the Claude CLI's by default)")
    parser.add_argument("--effort", default="", choices=("", "low", "medium", "high", "xhigh", "max"))
    parser.add_argument("--wait", action="store_true", help="wait for every job before each turn (no timing)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--allow-database", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    counter = (worlds.install_counting_provider(model=args.model, effort=args.effort) if args.provider == "route"
               else worlds.install_scripted_model())
    started = time.perf_counter()
    report = play(args.turns, args.seed, wait=args.wait)
    report = {"schema_version": 1, "measurement": "RPG areas filled in on arrival (EV-10)",
              "measured_on": date.today().isoformat(), "world": "aurelia",
              "provider": worlds.provider_identity(counter) if args.provider == "route" else {"provider": "scripted"},
              "elapsed_s": round(time.perf_counter() - started, 1), **report}
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"passed": report["passed"], **{name: check["passed"] for name, check in report["checks"].items()},
                      "arrivals": report["checks"]["filled_on_arrival"]}, indent=2))


if __name__ == "__main__":
    main()
