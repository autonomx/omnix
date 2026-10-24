"""Measure RPG turn latency per turn class against a provider (RQ-0.5).

Each turn class is played ``--runs`` times (default 20) in Aurelia, from the same scene snapshot each time:

| Class | Scene | What is played |
|---|---|---|
| look | Starfall Grove | "look around" |
| arrive | Starfall Grove | "go to Starfall Village" |
| question | Starfall Grove | "Liora, where am I?" |
| buy | Starfall Village | "buy a healing potion" |
| fight | Starfall Grove | "attack the echo wolf" |
| tactical_move | Starfall Grove, in a fight with an echo wolf | ``POST /api/rpg/map-instances/{id}/tactical/move``, one cell back and forth |
| status | Starfall Grove | "check my inventory" |
| wait | Starfall Grove | "wait" |

Per turn it records, from the request's start:

- ``outcome_known_ms``: the end of the turn's ``resolve`` stage, when the deterministic outcome is known on the
  server (the tactical route resolves and commits in one step, so it is the whole request);
- ``outcome_visible_ms``: when the play screen can show the outcome. Today that is the turn's response (the outcome
  arrives with the narration), so it equals ``complete_ms``;
- ``first_narration_ms``: the first non-empty narration draft the narrative writer publishes (what
  ``GET /api/rpg/sessions/{id}/turn-draft`` serves; the client adds up to its poll interval); null when the turn
  publishes no draft;
- ``complete_ms``: the turn's response;
- the model calls the turn made (count, role, time) and the non-model overhead (``complete_ms`` minus model time).

Providers: ``--provider route`` uses RPG's settings route (``rpg_llm_route``: Claude Haiku through the Claude CLI on
this install; there is no Anthropic API key here, so the roadmap's API reference model is not measured);
``--provider scripted`` answers every call with the role-keyed scripted model, which measures the harness and the
engine without a model.

The report (``docs/measurements/rpg-latency-<date>.json``) gives p50 and p95 per class and the F1/F3 checks.

    OMNIX_DATABASE_URL=postgresql://...@127.0.0.1:16432/<disposable db> \\
        python scripts/rpg_latency_harness.py --provider route --runs 20
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests.rehearsal.rpg.stats import summary  # noqa: E402

CLASSES: dict[str, dict[str, Any]] = {
    "look": {"scene": "grove", "command": "look around"},
    "arrive": {"scene": "grove", "command": "go to Starfall Village"},
    "question": {"scene": "grove", "command": "Liora, where am I?"},
    "buy": {"scene": "village", "command": "buy a healing potion"},
    "fight": {"scene": "grove", "command": "attack the echo wolf"},
    "tactical_move": {"scene": "fight", "command": None},
    "status": {"scene": "grove", "command": "check my inventory"},
    "wait": {"scene": "grove", "command": "wait"},
}
SCENE_SETUP = {"grove": [], "village": ["go to Starfall Village"], "fight": ["attack the echo wolf"]}
DETERMINISTIC = {"status", "wait", "tactical_move"}


class Clock:
    """Marks of the turn under way, from instrumented stage spans and narration drafts."""

    def __init__(self) -> None:
        self.started = 0.0
        self.resolve_done: float | None = None
        self.first_draft: float | None = None

    def reset(self) -> None:
        self.started = time.perf_counter()
        self.resolve_done = None
        self.first_draft = None


def instrument(clock: Clock) -> None:
    """Note when the resolve stage ends and when the narrative writer first publishes a draft."""
    from contextlib import contextmanager

    from app.apps.rpg.narration import narrative_provider
    from app.apps.rpg.session import pipeline

    original_span = pipeline.rpg_pipeline_span

    @contextmanager
    def span(name: str, *, fields: dict[str, Any] | None = None):
        with original_span(name, fields=fields) as stage:
            yield stage
        if name == "turn.stage.resolve":
            clock.resolve_done = time.perf_counter()

    original_publish = narrative_provider.publish_narration_draft

    def publish(text: str) -> None:
        if text and clock.first_draft is None:
            clock.first_draft = time.perf_counter()
        original_publish(text)

    setattr(pipeline, "rpg_pipeline_span", span)
    setattr(narrative_provider, "publish_narration_draft", publish)


def _ms(mark: float | None, start: float) -> float | None:
    return round((mark - start) * 1000, 1) if mark is not None else None


class Harness:
    def __init__(self, provider: str) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.apps.rpg.edge.api.feature_routes.rpg_session_routes import register_rpg_session_routes
        from app.apps.rpg.edge.api.feature_routes.rpg_tactical_spatial_routes import register_rpg_tactical_spatial_routes
        from tests.rehearsal.rpg import worlds
        from tests.support.routers import include_router_registrar

        self.worlds = worlds
        if provider == "scripted":
            self.model = worlds.install_scripted_model()
            self.calls = lambda: [{"role": role, "ms": 0.0} for role in self.model.calls]
        else:
            self.model = worlds.install_counting_provider()
            self.calls = lambda: list(self.model.calls)
        app = FastAPI()
        include_router_registrar(app, register_rpg_session_routes)
        include_router_registrar(app, register_rpg_tactical_spatial_routes)
        self.client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "rpg-latency"},
                                 raise_server_exceptions=False)
        self.clock = Clock()
        instrument(self.clock)
        self.session_id = ""
        self.snapshots: dict[str, dict[str, Any]] = {}

    def turn(self, command: str) -> int:
        response = self.client.post(f"/api/rpg/sessions/{self.session_id}/turn", json={"command": command},
                                    headers={"x-omnix-rpg-submission-id": f"submit:latency:{uuid.uuid4().hex}"})
        return response.status_code

    def restore(self, scene: str) -> None:
        from app.apps.rpg.session.service import save_session

        current = self.worlds.load(self.session_id)
        restored = copy.deepcopy(self.snapshots[scene])
        restored.setdefault("runtime_state", {})["state_revision"] = (current.get("runtime_state") or {}).get("state_revision")
        save_session(restored)

    def prepare(self) -> dict[str, Any]:
        self.session_id = self.worlds.launch("aurelia")
        self.turn("look around")
        opening = self.worlds.load(self.session_id)
        self.snapshots["grove"] = opening
        for scene, commands in SCENE_SETUP.items():
            if not commands:
                continue
            self.snapshots[scene] = opening
            self.restore(scene)
            for command in commands:
                self.turn(command)
            self.snapshots[scene] = self.worlds.load(self.session_id)
        return {scene: {"location": (snapshot.get("simulation_state") or {}).get("location_id"),
                        "combat_active": ((snapshot.get("simulation_state") or {}).get("combat_state") or {}).get("active") is True}
                for scene, snapshot in self.snapshots.items()}

    def _map_instance(self) -> dict[str, Any]:
        from app.persistence.unit_of_work import unit_of_work

        with unit_of_work() as work:
            rows = work.connection.execute(
                "SELECT map_instance_id, map_state_revision, snapshot_jsonb FROM omnix_rpg_campaign_map_instances "
                "WHERE campaign_id = %s AND location_id = %s",
                (self.session_id, "location:aurelia:arrival-grove"),
            ).fetchall()
            campaign = work.connection.execute(
                "SELECT revision FROM omnix_rpg_campaigns WHERE id = %s", (self.session_id,)).fetchone()
            work.rollback()
        if not rows:
            raise RuntimeError("the grove has no map instance")
        instance_id, map_revision, snapshot = rows[0]
        return {"id": instance_id, "map_revision": int(map_revision), "campaign_revision": int(campaign[0]),
                "snapshot": snapshot}

    def tactical_move(self, step: int) -> int:
        instance = self._map_instance()
        player = next(actor for actor in instance["snapshot"].get("actors") or ()
                      if str(actor.get("actor_id") or "").startswith("player:"))
        x, y = player["cell"]
        destination = [x, y + 1] if step % 2 == 0 else [x, y - 1]
        submission = f"submit:latency:{uuid.uuid4().hex}"
        response = self.client.post(f"/api/rpg/map-instances/{instance['id']}/tactical/move", json={
            "submission_id": submission, "command_id": f"command:{submission}", "actor_id": player["actor_id"],
            "destination": destination, "expected_map_state_revision": instance["map_revision"],
            "expected_campaign_revision": instance["campaign_revision"],
        })
        return response.status_code

    def run_class(self, name: str, runs: int) -> list[dict[str, Any]]:
        spec = CLASSES[name]
        rows = []
        for index in range(runs):
            self.restore(spec["scene"])
            calls_before = len(self.calls())
            self.clock.reset()
            status = self.tactical_move(index) if spec["command"] is None else self.turn(spec["command"])
            done = time.perf_counter()
            start = self.clock.started
            calls = self.calls()[calls_before:]
            model_ms = round(sum(float(call.get("ms") or 0) for call in calls), 1)
            complete = _ms(done, start)
            rows.append({
                "http": status,
                "outcome_known_ms": complete if spec["command"] is None else _ms(self.clock.resolve_done, start),
                "outcome_visible_ms": complete,
                "first_narration_ms": _ms(self.clock.first_draft, start),
                "complete_ms": complete,
                "model_calls": len(calls),
                "model_roles": [call.get("role") for call in calls],
                "model_ms": model_ms,
                "overhead_ms": round((complete or 0) - model_ms, 1),
            })
            print(f"{name} {index + 1}/{runs}: {status} {complete} ms, {len(calls)} calls", file=sys.stderr)
        return rows


def class_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def values(key: str) -> list[float]:
        return [float(row[key]) for row in rows if row.get(key) is not None]

    return {
        "runs": len(rows),
        "http_statuses": sorted({row["http"] for row in rows}),
        "outcome_known_ms": summary(values("outcome_known_ms")),
        "outcome_visible_ms": summary(values("outcome_visible_ms")),
        "first_narration_ms": summary(values("first_narration_ms")),
        "first_narration_published": sum(row["first_narration_ms"] is not None for row in rows),
        "complete_ms": summary(values("complete_ms")),
        "model_calls": summary(values("model_calls")),
        "model_ms": summary(values("model_ms")),
        "overhead_ms": summary(values("overhead_ms")),
        "model_roles": sorted({role for row in rows for role in row["model_roles"]}),
    }


def checks(classes: dict[str, Any], rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    every = [row for group in rows.values() for row in group]
    return {
        "F3_turns_with_at_most_one_call": round(sum(row["model_calls"] <= 1 for row in every) / len(every), 3) if every else None,
        "F3_max_calls_per_turn": max((row["model_calls"] for row in every), default=None),
        "F3_deterministic_turns_with_a_call": sum(row["model_calls"] > 0 for name in DETERMINISTIC for row in rows.get(name, [])),
        "F1_first_narration_p95_ms": {name: report["first_narration_ms"]["p95"] for name, report in classes.items()},
        "F1_complete_p50_ms": {name: report["complete_ms"]["p50"] for name, report in classes.items()},
        "F1_complete_p95_ms": {name: report["complete_ms"]["p95"] for name, report in classes.items()},
        "targets": {
            "outcome_p95": "<= 300 ms tactical moves and attacks; <= 1.0 s other grammar-parsed and structured; <= 3.0 s with an intent call",
            "first_narration_p95": "<= 2.5 s", "complete": "p50 <= 6 s, p95 <= 10 s",
            "deterministic": "status, equip, inventory, wait <= 500 ms complete, no model call",
            "F3": ">= 80% of turns at most one call; deterministic turns none; no turn more than two",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--provider", choices=("route", "scripted"), default="scripted")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--classes", nargs="+", choices=tuple(CLASSES), default=list(CLASSES))
    parser.add_argument("--allow-database", default="", help="a disposable database whose name lacks 'test'/'bench'")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    os.environ.setdefault("OMNIX_RPG_TURNS_PER_HOUR", "0")
    if args.provider == "route":
        # Tests pin the narrative writer to deterministic prose; a latency run uses the model.
        os.environ["OMNIX_RPG_NARRATIVE_WRITER_MODE"] = "auto"
    from tests.rehearsal.rpg import worlds

    database = worlds.require_disposable_database(args.allow_database)
    worlds.bootstrap()
    harness = Harness(args.provider)
    identity = worlds.provider_identity() if args.provider == "route" else {"provider": "scripted", "model": "scripted"}
    started = time.perf_counter()
    scenes = harness.prepare()
    rows = {name: harness.run_class(name, args.runs) for name in args.classes}
    classes = {name: class_report(group) for name, group in rows.items()}
    report = {
        "schema_version": 1,
        "measurement": "RPG turn latency per turn class (RQ-0.5)",
        "measured_on": date.today().isoformat(),
        "revision": subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip(),
        "database": database,
        "provider": {**identity, "resolved_models": sorted(getattr(harness.model, "resolved_models", ()))},
        "world": "aurelia",
        "scenes": scenes,
        "runs_per_class": args.runs,
        "classes": classes,
        "checks": checks(classes, rows),
        "notes": [
            "outcome_visible_ms equals complete_ms: today the outcome reaches the play screen with the turn's response.",
            "first_narration_ms is when the narrative writer first publishes a non-empty draft on the server; the "
            "play screen polls GET .../turn-draft, which adds up to its poll interval.",
            "Each run starts from the class's scene snapshot, restored by an out-of-turn save.",
        ],
        "elapsed_s": round(time.perf_counter() - started, 1),
        "rows": rows,
    }
    output = args.output or ROOT / "docs/measurements" / f"rpg-latency-{date.today().isoformat()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({name: {"complete_p50": c["complete_ms"]["p50"], "complete_p95": c["complete_ms"]["p95"],
                             "calls_p50": c["model_calls"]["p50"]} for name, c in classes.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
