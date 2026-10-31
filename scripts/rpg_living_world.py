"""Play Aurelia for 200 turns with idle gaps and check that its world lives (W1, roadmap §2).

A scripted player lives in the world: a day's round of the village and the guild (looking, waiting, talking to whoever
is there), then a hunt at Skybridge Pass, each fight fought to its end (the felled wolves pull Cloudspine's road
pressure down, as a world's levers are pulled; quests.md), then a night at the inn; when hurt it goes back to rest. It
takes a step on the local grid now and then and goes away every so often (``POST /resume``: the world catches up). The
model is the role-keyed scripted one, so the run is deterministic. Every turn that lets time pass is recorded through the
world tick (``session/turn/world_tick.world_tick``): who moved, who the hero sees come and go, which of the world's
pressures turned, and what reached the hero of it. The checks (W1's target):

- every named person has a routine (an authored schedule in the world model);
- at least one pressure transition (escalated, contained, resolved, stirring again) in every 50 turns;
- at least one player-visible world event (someone arriving or leaving, word of a pressure) in every 20 turns;
- who is present changes with the time of day: some place shows different people at different times;
- returning after idle time lists only real changes: each "arrives" and "leaves" in a return's recap is a person
  who came or went in that tick, and each "Word comes" a pressure that turned in it;
- the run replays: from its snapshots the stored turn patches rebuild every turn's ``state_hash_after``
  (``scripts/rpg_replay_audit.py``), and each local map's event log, applied to the snapshot it was created with,
  rebuilds the grid as stored;
- with ``--reexecute``, the run is re-executed (evolution roadmap D1): a second campaign, launched the same way, is
  sent the same inputs, each intent call answered by the reading the first run was given and each turn folding in
  the proposals the first run's turn row recorded (``folded_proposals_jsonb``), and after every input its document,
  ids and times normalized, must hash as the first run's did.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_living_world.py [--turns 1000] [--reexecute] --output docs/measurements/rpg-living-world-<date>.json
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

PRESSURE_KINDS = ("pressure_escalated", "pressure_contained", "pressure_resolved", "pressure_reactivated")
# The scripted player's round: "{person}" is the first person present.
ROUND = ("go to Starfall Village", "look around", "talk to {person}", "wait a while", "ask {person} about work",
         "go to the Wayfarers' Guild", "look around", "talk to {person}", "wait a while", "go to Starfall Village",
         "go to Skybridge Pass", "attack the echo wolf", "look around", "attack the echo wolf", "go to Starfall Village",
         "rest until morning", "look around", "wait a while", "go to Starfall Grove", "look around")
IDLE_EVERY = 25  # a return after time away, every this many turns
IDLE_SECONDS = 3600  # longer than the catch-up's cap, so each return catches up as far as it may
HEARD_EVERY = 50  # a name heard in narration (a ``heard_of`` proposal, EV-11), every this many turns, from turn 10
GRID_STEP_EVERY = 5  # a step on the local grid the hero stands on, every this many turns


# --- the checks (pure, over what the run recorded) ------------------------------------------------------------

def windows(turns: int, size: int) -> list[range]:
    return [range(start, min(start + size, turns)) for start in range(0, turns, size)]


def every_window_has(marks: set[int], turns: int, size: int) -> dict[str, Any]:
    """Whether each ``size``-turn window of the run holds a marked turn (a last, shorter window counts if full)."""
    missing = [f"{span.start}-{span.stop - 1}" for span in windows(turns, size)
               if len(span) == size and not marks.intersection(span)]
    return {"windows": len([span for span in windows(turns, size) if len(span) == size]), "missing": missing,
            "passed": not missing}


def presence_by_time(seen: list[dict[str, Any]]) -> dict[str, Any]:
    """The places that showed different people at different times of day."""
    by_place: dict[str, dict[str, set[tuple[str, ...]]]] = {}
    for row in seen:
        by_place.setdefault(row["location_id"], {}).setdefault(row["part_of_day"], set()).add(tuple(row["present"]))
    changing = sorted(place for place, parts in by_place.items()
                      if len({people for sets in parts.values() for people in sets}) > 1 and len(parts) > 1)
    return {"places_seen": len(by_place), "places_changing_with_time": changing, "passed": bool(changing)}


def recap_is_real(lines: list[str], *, arrived: set[str], left: set[str], turned: set[str]) -> list[str]:
    """The recap lines naming no real change: an arrival or departure that did not happen, word of a pressure
    that did not turn. ``arrived``/``left`` are names, ``turned`` pressure names."""
    false = []
    for line in lines:
        if line.startswith("Word comes:"):
            if not any(name and name in line for name in turned):
                false.append(line)
        elif " arrives" in line:
            if not any(line.startswith(name + " arrives") for name in arrived):
                false.append(line)
        elif " leaves" in line:
            if not any(line.startswith(name + " leaves") for name in left):
                false.append(line)
    return false


def part_of_day(minute: int) -> str:
    hour = (minute // 60) % 24
    return "night" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


# --- the run --------------------------------------------------------------------------------------------------

class Recorder:
    """What each world tick did, by turn: the people who moved, the presence before and after, events, lines."""

    def __init__(self) -> None:
        from app.apps.rpg.foundation.persistence import rpg_map_instance_repository as maps
        from app.apps.rpg.session.turn import run

        self.ticks: list[dict[str, Any]] = []
        self.initial_maps: dict[str, dict[str, Any]] = {}
        world_tick = run.world_tick

        def recorded(document: Any, **kwargs: Any) -> Any:
            from app.apps.rpg.foundation.state import access as sections
            from app.apps.rpg.rules import routines

            changes, receipt, seen = world_tick(document, **kwargs)
            simulation = sections.simulation_state_of(document) or {}
            _, before = routines.present_now(simulation)
            after = next((list(change.present_npc_ids) for change in changes if change.type == "presence_changed"),
                         before)
            ticked = next((change for change in changes if change.type == "world_ticked"), None)
            events = [str(event) for event in ((ticked.summary.get("event_ids") if ticked else None) or ())]
            self.ticks.append({"before": list(before), "after": after, "events": events, "seen": list(seen),
                               "minutes": int(kwargs.get("minutes") or 0)})
            return changes, receipt, seen

        setattr(run, "world_tick", recorded)
        create = maps.PostgresRpgMapInstanceRepository.create_instance

        def created(repository: Any, context: Any, **kwargs: Any) -> Any:
            self.initial_maps.setdefault(str(kwargs["map_instance_id"]), dict(kwargs["snapshot"]))
            return create(repository, context, **kwargs)

        setattr(maps.PostgresRpgMapInstanceRepository, "create_instance", created)


class LivingPlayer:
    """The scripted round, with a fight fought to its end and a rest when hurt."""

    def __init__(self) -> None:
        self.step = 0

    def next(self, state: dict[str, Any]) -> str:
        simulation = state.get("simulation_state") or {}
        if ((simulation.get("combat_state") or {}).get("active")) is True:
            return "attack the echo wolf"
        hp = ((simulation.get("player_state") or {}).get("resources") or {}).get("hp") or {}
        if hp.get("max") and int(hp.get("current") or 0) < 0.4 * int(hp["max"]):
            here = str(simulation.get("current_location_id") or "")
            return "rest until morning" if here.endswith("starfall-village") else "go to Starfall Village"
        command = ROUND[self.step % len(ROUND)]
        self.step += 1
        if "{person}" in command:
            from app.apps.rpg.rules import routines

            _, present = routines.present_now(simulation)
            people = (simulation.get("world_model") or {}).get("npcs") or {}
            names = [str((people.get(npc) or {}).get("name") or "") for npc in present]
            return command.format(person=next((name for name in names if name), "someone")) if names else "look around"
        return command


class Run:
    def __init__(self, turns: int, *, replaying: "Run | None" = None) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
        from app.apps.rpg.edge.api.feature_routes.rpg_tactical_spatial_routes import register_rpg_tactical_spatial_routes
        from tests.rehearsal.rpg import worlds
        from tests.support.routers import include_router_registrar

        self.worlds = worlds
        self.turns = turns
        self.model = worlds.install_scripted_model()
        self.replaying = replaying  # the first run this one re-executes
        self.inputs: list[dict[str, Any]] = []  # each input sent: its intent answers, its folds, the hash after it
        self.recorder = Recorder()
        app = FastAPI()
        include_router_registrar(app, register_rpg_session_routes)
        include_router_registrar(app, register_rpg_tactical_spatial_routes)
        self.client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "rpg-living-world"})
        self.rows: list[dict[str, Any]] = []
        self.presence: list[dict[str, Any]] = []
        self.returns: list[dict[str, Any]] = []

    def _state(self) -> dict[str, Any]:
        return self.worlds.load(self.session_id)

    def _grid_step(self, step: int) -> int | None:
        from app.persistence.unit_of_work import unit_of_work

        with unit_of_work() as work:
            row = work.connection.execute(
                "SELECT i.map_instance_id, i.map_state_revision, i.snapshot_jsonb, c.revision "
                "FROM omnix_rpg_campaigns c JOIN omnix_rpg_campaign_map_instances i "
                "ON i.campaign_id = c.id AND i.map_instance_id = c.state_jsonb->'state'->>'current_map_instance_id' "
                "WHERE c.id = %s", (self.session_id,)).fetchone()
            work.rollback()
        if row is None:
            return None
        instance_id, map_revision, snapshot, campaign_revision = row
        player = next((actor for actor in snapshot.get("actors") or ()
                       if str(actor.get("actor_id") or "").startswith("player:")), None)
        if player is None:
            return None
        x, y = player["cell"]
        submission = f"submit:living:{self.session_id}:{step}"  # the campaign's own: the same when re-executed
        response = self.client.post(f"/api/rpg/map-instances/{instance_id}/tactical/move", json={
            "submission_id": submission, "command_id": f"command:{submission}", "actor_id": player["actor_id"],
            "destination": [x, y + 1] if step % 2 == 0 else [x, y - 1],
            "expected_map_state_revision": int(map_revision), "expected_campaign_revision": int(campaign_revision)})
        return response.status_code

    def _observe(self, turn: int) -> None:
        from app.apps.rpg.rules import routines
        from app.apps.rpg.session.turn.world_tick import clock_minute

        state = self._state()
        simulation = state.get("simulation_state") or {}
        where, present = routines.present_now(simulation)
        self.presence.append({"turn": turn, "location_id": where, "present": sorted(present),
                              "part_of_day": part_of_day(clock_minute(state))})

    def _turn_folds(self) -> list[list[dict[str, Any]]]:
        """What each of the campaign's committed turn rows folded in, oldest first."""
        from app.persistence.unit_of_work import unit_of_work

        with unit_of_work() as work:
            rows = work.connection.execute(
                "SELECT folded_proposals_jsonb FROM omnix_rpg_turns WHERE campaign_id = %s ORDER BY sequence",
                (self.session_id,)).fetchall()
            work.rollback()
        return [list((row[0] or {}).get("folded") or ()) for row in rows]

    def _send(self, send: Any) -> Any:
        """One input: re-executed, answered and folded as the first run's same input was; its record, and the
        document's normalized hash after it."""
        from app.apps.rpg.session.turn.proposals import replay_folded
        from tests.characterization.test_rpg_published_world_golden import _document_hash

        index = len(self.inputs)
        first = self.replaying.inputs[index] if self.replaying is not None else None
        if first is not None:
            self.model.recorded = list(first["answers"])
            replay_folded(self.session_id, [row for turn in first["folds"] for row in turn])
        read, rows = len(self.model.read), len(self._turn_folds())
        response = send()
        if first is not None:
            from app.apps.rpg.session.turn import proposals

            proposals._REPLAY.pop(self.session_id, None)  # an input that loaded no turn leaves nothing behind
        state = self._state()
        world_id = str((state.get("manifest") or {}).get("world_id") or "")
        self.inputs.append({"answers": self.model.read[read:], "folds": self._turn_folds()[rows:],
                            "hash": _document_hash(state, self.session_id, world_id)})
        return response

    def _hear_of_someone(self, turn: int) -> None:
        """A person the hero does not know, named in narration: a proposal the next turn folds in (EV-11)."""
        from app.apps.rpg.foundation.state.proposals import Proposal
        from app.apps.rpg.rules.hero_knowledge import known_entries, world_entries
        from app.apps.rpg.session.turn.proposals import record_proposals

        state = self._state()
        simulation = state.get("simulation_state") or {}
        known = known_entries(simulation)
        person = next((entry for entry, row in sorted(world_entries(simulation).items())  # one the hero may hear of
                       if row["family"] == "person" and entry not in known
                       and row.get("hidden") is not True and row.get("secret") is not True), "")
        if person:
            from app.apps.rpg.session.persistence.session_records import load_session_version_from_postgres

            revision = int((load_session_version_from_postgres(self.session_id) or (0,))[0])
            record_proposals(self.session_id, [Proposal(
                proposal_id=f"proposal:living-heard:{turn}", kind="heard_of", source="narration",
                after_revision=revision, payload={"entry_id": person})])

    def play(self) -> None:
        self.session_id = self.worlds.launch("aurelia")
        if self.replaying is not None:  # re-executed: every intent answer is the first run's, none read again
            self.model.session_id = ""
        player = LivingPlayer()
        for turn in range(self.turns):
            ticks_before = len(self.recorder.ticks)
            if self.replaying is None and turn % HEARD_EVERY == 10:  # re-executed, folded from the turn rows instead
                self._hear_of_someone(turn)
            if turn and turn % IDLE_EVERY == 0:
                response = self._send(lambda: self.client.post(f"/api/rpg/sessions/{self.session_id}/resume",
                                                               json={"elapsed_seconds": IDLE_SECONDS}))
                kind, said = "return", "(time away)"
            else:
                # Re-executed, the first run's own commands are sent again (not chosen again).
                said = self.replaying.rows[turn]["command"] if self.replaying is not None else player.next(self._state())
                response = self._send(lambda: self.client.post(f"/api/rpg/sessions/{self.session_id}/turn",
                                                               json={"command": said}))
                kind = "turn"
            ticks = self.recorder.ticks[ticks_before:]
            body = response.json() if response.status_code == 200 else {}
            outcome = body.get("outcome") if isinstance(body.get("outcome"), dict) else {}
            planned = outcome.get("planned_action")
            reply = {"mechanic": planned.get("mechanic") if isinstance(planned, dict) else planned,
                     "changes": sorted({str(change.get("type")) for change in outcome.get("applied_changes") or ()
                                        if isinstance(change, dict)})}
            self.rows.append({"turn": turn, "kind": kind, "command": said, "status": response.status_code, "reply": reply,
                              "events": [event for tick in ticks for event in tick["events"]],
                              "seen": [line for tick in ticks for line in tick["seen"]]})
            if kind == "return":
                self.returns.append({"turn": turn, "ticks": ticks})
            self._observe(turn)
            if turn % GRID_STEP_EVERY == 0:
                self._send(lambda: self._grid_step(turn // GRID_STEP_EVERY))

    # --- the report ---------------------------------------------------------------------------------------

    def report(self) -> dict[str, Any]:
        from app.apps.rpg.rules import routines

        state = self._state()
        world_model = (state.get("simulation_state") or {}).get("world_model") or {}
        people = world_model.get("npcs") or {}
        schedules = routines._schedules(world_model)
        unscheduled = sorted(npc_id for npc_id, row in people.items()
                             if (row or {}).get("name") and not schedules.get(npc_id))
        pressure_turns = {row["turn"] for row in self.rows
                          if any(event.rsplit(":", 1)[-1] in PRESSURE_KINDS for event in row["events"])}
        visible_turns = {row["turn"] for row in self.rows if row["seen"]}
        names = {npc_id: str((row or {}).get("name") or npc_id) for npc_id, row in people.items()}
        plan = {}
        for row in ((state.get("simulation_state") or {}).get("causal_world_runtime") or {}).get(
                "pressure_plan", {}).get("pressures") or ():
            plan[str(row.get("pressure_id"))] = str(row.get("name") or row.get("pressure_id"))
        false_recaps = []
        for back in self.returns:
            for tick in back["ticks"]:
                arrived = {names.get(npc, npc) for npc in tick["after"] if npc not in tick["before"]}
                left = {names.get(npc, npc) for npc in tick["before"] if npc not in tick["after"]}
                turned = {name for pressure_id, name in plan.items()
                          if any(f":{pressure_id}:" in event for event in tick["events"])}
                false_recaps += recap_is_real(tick["seen"], arrived=arrived, left=left, turned=turned)
        checks = {
            "every_named_person_has_a_routine": {"people": len(people), "without_routine": unscheduled,
                                                 "passed": bool(people) and not unscheduled},
            "pressure_transition_every_50_turns": {**every_window_has(pressure_turns, len(self.rows), 50),
                                                   "turns_with_one": len(pressure_turns)},
            "visible_world_event_every_20_turns": {**every_window_has(visible_turns, len(self.rows), 20),
                                                   "turns_with_one": len(visible_turns)},
            "presence_changes_with_time_of_day": presence_by_time(self.presence),
            "returns_list_only_real_changes": {"returns": len(self.returns), "false_lines": false_recaps,
                                               "passed": bool(self.returns) and not false_recaps},
            "replays": self.replay(),
        }
        return {
            "schema_version": 1,
            "measurement": "RPG living world (W1)",
            "measured_on": date.today().isoformat(),
            "revision": subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=ROOT, capture_output=True,
                                       text=True).stdout.strip(),
            "world": "aurelia",
            "turns": len(self.rows),
            "refused_or_failed": [row for row in self.rows if row["status"] != 200],
            "checks": checks,
            "passed": all(check["passed"] for check in checks.values()),
            "rows": self.rows,
        }

    def reexecuted(self, again: "Run") -> dict[str, Any]:
        """The re-executed run against this one: after each input, the same normalized document."""
        pairs = list(zip(self.inputs, again.inputs))
        mismatched = [index for index, (first, second) in enumerate(pairs) if first["hash"] != second["hash"]]
        # The re-executed run was given the first's answers, input by input, and folded what its turn rows recorded.
        answered_otherwise = [index for index, (first, second) in enumerate(pairs) if first["answers"] != second["answers"]]
        folded_otherwise = [index for index, (first, second) in enumerate(pairs) if first["folds"] != second["folds"]]
        answers = sum(len(row["answers"]) for row in self.inputs)
        folded = sum(len(turn) for row in self.inputs for turn in row["folds"])
        return {"inputs": len(self.inputs), "reexecuted_inputs": len(again.inputs), "mismatched": mismatched[:20],
                "first_mismatch": mismatched[0] if mismatched else None,
                "answered_otherwise": answered_otherwise[:20], "folded_otherwise": folded_otherwise[:20],
                "intent_answers": answers, "folded": folded,
                "passed": bool(self.inputs) and len(again.inputs) == len(self.inputs) and not mismatched
                and not answered_otherwise and not folded_otherwise and answers > 0 and folded > 0}

    def replay(self) -> dict[str, Any]:
        import rpg_replay_audit as audit
        from app.apps.rpg.foundation.persistence.rpg_map_instance_repository import PostgresRpgMapInstanceRepository
        from app.apps.rpg.world.map_instance_runtime import (
            ActorMovedEvent,
            CampaignMapInstanceSnapshot,
            replay_map_events,
        )
        from app.persistence.unit_of_work import unit_of_work
        from app.security.tenant_context import current_tenant

        audited = audit.run(os.environ["OMNIX_DATABASE_URL"], [self.session_id])
        campaign = (audited.get("campaigns") or [{}])[0]
        maps: dict[str, bool] = {}
        with unit_of_work() as work:
            repository = PostgresRpgMapInstanceRepository(work.connection)
            for instance_id, initial in self.recorder.initial_maps.items():
                stored = repository.get_instance(current_tenant(), instance_id)
                events = repository.list_events(current_tenant(), instance_id)
                rebuilt = replay_map_events(CampaignMapInstanceSnapshot.model_validate(initial),
                                            [ActorMovedEvent.model_validate(event) for event in events])
                maps[instance_id] = stored is not None and rebuilt.model_dump(mode="json") == stored["snapshot"]
            work.rollback()
        turns = int(campaign.get("turn_rows") or 0)
        verified = int(campaign.get("verified_turns") or 0)
        current = bool(campaign.get("replay_reaches_current")) and bool(campaign.get("replay_matches_current"))
        return {"turns": turns, "verified_turns": verified, "mismatched_turns": campaign.get("mismatched_turns"),
                "hash_chain_breaks": campaign.get("hash_chain_breaks"), "reaches_and_matches_current": current,
                "maps": maps, "map_instances_replayed": len(maps),
                "passed": bool(turns) and verified == turns and current and all(maps.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--turns", type=int, default=200)
    parser.add_argument("--allow-database", default="", help="a disposable database whose name lacks 'test'/'bench'")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reexecute", action="store_true", help="re-execute the run on a second campaign (D1)")
    args = parser.parse_args(argv)
    os.environ.setdefault("OMNIX_RPG_TURNS_PER_HOUR", "0")
    os.environ["OMNIX_RPG_NARRATIVE_WRITER_MODE"] = "deterministic"
    from tests.rehearsal.rpg import worlds

    worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    run = Run(args.turns)
    run.play()
    report = run.report()
    if args.reexecute:
        again = Run(args.turns, replaying=run)
        again.play()
        report["checks"]["reexecuted"] = run.reexecuted(again)
        report["passed"] = all(check["passed"] for check in report["checks"].values())
    text = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"passed": report["passed"], **{name: check["passed"] for name, check in report["checks"].items()}},
                     indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
