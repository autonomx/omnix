from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

from app.rpg.core.action_resolver import ActionResolver, ResolutionStrategy
from app.rpg.core.determinism import stable_json
from app.rpg.core.execution_pipeline import ExecutionPipeline
from app.rpg.core.probabilistic_executor import ProbabilisticActionExecutor
from app.runtime.clock import TurnContext, bind_turn_context
from tests.characterization.fakes import FakeLLMProvider, prompt_digest
from tests.characterization.harness import capture


SESSION_SEED = 0x7A11CE
TURN_COUNT = 20
START_TIME = datetime(2026, 9, 28, 9, tzinfo=timezone.utc)


class RecordedClock:
    def __init__(self) -> None:
        self.current = START_TIME

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return float(self.current.timestamp())


class TurnWorld:
    def __init__(self) -> None:
        self.time = 0


class TurnMemory:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def add_events(self, events: list[dict], *, current_tick: int) -> None:
        self.events.extend({**event, "stored_at_tick": current_tick} for event in events)


class TurnArcs:
    def update_arcs(self, events: list[dict]) -> list[dict]:
        return [
            {"arc_event": event.get("type", "unknown")}
            for event in events
        ]


class TurnDirector:
    def update(self, session: dict, events: list[dict]) -> None:
        simulation = session["simulation_state"]
        simulation["event_log"].extend(deepcopy(events))
        simulation["turn_index"] += 1


def _scheduled_response(turn: int, scenario: str) -> dict:
    action = {
        "action": {
            "combat": "attack",
            "dialogue": "persuade",
            "item_use": "use_item",
            "travel": "move",
            "idle": "wait",
            "first_call": "observe",
            "fast_path": "inspect",
        }[scenario],
        "npc_id": "mara",
        "target": f"target:{scenario}",
        "source": "player",
        "intent_tick": turn,
        "success_rate": 0.72,
    }
    actions = [action]
    if scenario == "fast_path":
        actions.append(
            {
                **action,
                "action": "wait",
                "source": "companion",
                "success_rate": 0.81,
            }
        )
    return {
        "actions": actions,
        "visible_response": f"Turn {turn + 1}: {scenario.replace('_', ' ')} resolved.",
    }


def _scenario_output() -> dict:
    schedule = ("first_call", "combat", "dialogue", "item_use", "travel", "idle", "fast_path")
    recorded_inputs = tuple(
        {
            "player_input": f"recorded {schedule[turn % len(schedule)]} command {turn:02d}",
            "now": (START_TIME + timedelta(seconds=turn)).isoformat(),
            "scenario": schedule[turn % len(schedule)],
        }
        for turn in range(TURN_COUNT)
    )
    scripts = {
        prompt_digest([{"role": "user", "content": row["player_input"]}]): json.dumps(
            _scheduled_response(turn, str(row["scenario"])),
            sort_keys=True,
        )
        for turn, row in enumerate(recorded_inputs)
    }

    def play() -> list[dict]:
        provider = FakeLLMProvider(scripts)
        world = TurnWorld()
        memory = TurnMemory()
        session = {
            "session_id": "characterization-rpg-turn",
            "simulation_state": {
                "rng_seed": SESSION_SEED,
                "turn_index": 0,
                "world_time": 0,
                "event_log": [],
            },
        }
        clock = RecordedClock()
        pipeline = ExecutionPipeline(
            resolver=ActionResolver(strategy=ResolutionStrategy.RANDOM),
            executor=ProbabilisticActionExecutor(),
            world=world,
            memory_manager=memory,
            arc_manager=TurnArcs(),
            director=TurnDirector(),
            clock=clock,
        )
        turns: list[dict] = []

        for turn, recorded in enumerate(recorded_inputs):
            prompt = [{"role": "user", "content": recorded["player_input"]}]
            provider_response = provider.chat_completion(messages=prompt)
            generated = json.loads(provider_response.content)
            clock.current = datetime.fromisoformat(recorded["now"])
            context = TurnContext.capture(
                clock,
                session_seed=SESSION_SEED,
                turn_index=turn,
                session_id=str(session["session_id"]),
                now=clock.current,
            )
            with bind_turn_context(context):
                result = pipeline.execute_turn(
                    session,
                    generated["actions"],
                    player_input=recorded["player_input"],
                )
            session["simulation_state"]["world_time"] = world.time
            turns.append(
                {
                    "turn": turn,
                    "scenario": recorded["scenario"],
                    "visible_response": generated["visible_response"],
                    "events": result["events"],
                    "director_feedback": result["director_feedback"],
                    "arc_updates": result["arc_updates"],
                    "state_hash": hashlib.sha256(
                        stable_json(session["simulation_state"]).encode("utf-8")
                    ).hexdigest(),
                }
            )

        assert len(provider.calls) == TURN_COUNT
        assert len(memory.events) == sum(len(turn["events"]) for turn in turns)
        assert pipeline._turn_counter == TURN_COUNT
        return turns

    first = play()
    replayed = play()
    assert first == replayed
    assert {turn["scenario"] for turn in first} == {
        "combat",
        "dialogue",
        "item_use",
        "travel",
        "idle",
        "first_call",
        "fast_path",
    }
    assert all(turn["events"] for turn in first)
    return {"turns": first}


def test_rpg_turn_pipeline_matches_seeded_characterization() -> None:
    capture("rpg-turn", _scenario_output)
