from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from app.apps.rpg.rules.action_resolver import resolve_player_action
from app.apps.rpg.foundation.core.determinism import (
    deterministic_turn_uuid,
    rng_for,
    rng_for_current_turn,
    rng_seed_from_session_id,
    stable_json,
    turn_rng_identity,
)
from app.apps.rpg.foundation.core.clock import DeterministicClock
from app.apps.rpg.foundation.core.event_bus import DeterminismConfig, Event, EventBus
from app.apps.rpg.session.idle_time import recorded_idle_tick_time
from app.runtime.clock import Clock, TurnContext, bind_turn_context, utc_now
from app.apps.rpg.session import service as session_service
from app.apps.rpg.world.political_system import PoliticalSystem
from tests.characterization.fakes import FakeLLMProvider, prompt_digest


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value
        self.now_calls = 0

    def now(self) -> datetime:
        self.now_calls += 1
        return self.value

    def monotonic(self) -> float:
        return 42.0


def test_turn_rng_is_stable_and_namespaced_by_purpose() -> None:
    def draws(turn_index: int, purpose: str) -> tuple[int, ...]:
        rng = rng_for(91, turn_index, purpose)
        return tuple(rng.randint(1, 20) for _ in range(4))

    first = draws(4, "player_action")

    assert first == draws(4, "player_action")
    assert first != draws(5, "player_action")
    assert first != draws(4, "npc_action")


def test_legacy_session_seed_uses_the_documented_sha256_upcaster() -> None:
    expected = int.from_bytes(hashlib.sha256(b"old-session-7").digest()[:8], "big")
    assert rng_seed_from_session_id("old-session-7") == expected


def test_legacy_campaign_seed_does_not_override_the_session_id_upcast() -> None:
    session = session_service.create_or_normalize_session(
        {
            "session_id": "old-session-legacy-seed",
            "simulation_state": {"seed": 1234},
            "runtime_state": {},
        }
    )

    assert session["simulation_state"]["rng_seed"] == rng_seed_from_session_id(
        "old-session-legacy-seed"
    )


def test_turn_rng_identity_prefers_context_and_upcasts_legacy_state() -> None:
    session = {
        "session_id": "legacy-pipeline-session",
        "simulation_state": {"seed": 1234, "turn_index": 8},
    }
    assert turn_rng_identity(session, 99) == (
        rng_seed_from_session_id("legacy-pipeline-session"),
        8,
    )

    context = TurnContext.capture(
        FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc)),
        session_seed=55,
        turn_index=4,
    )
    with bind_turn_context(context):
        assert turn_rng_identity(session, 99) == (55, 4)


def test_legacy_session_seed_is_persisted_on_the_next_save(monkeypatch) -> None:
    expected = rng_seed_from_session_id("old-session-8")
    captured: dict[str, object] = {}
    monkeypatch.setattr(session_service, "assert_session_integrity", lambda _session: None)
    monkeypatch.setattr(session_service, "load_session_from_disk", lambda _session_id: None)
    monkeypatch.setattr(
        session_service,
        "save_session_to_disk",
        lambda session, compact=False: captured.update(session=session) or session,
    )

    saved = session_service.save_session(
        {
            "session_id": "old-session-8",
            "simulation_state": {},
            "runtime_state": {},
        }
    )

    assert saved["simulation_state"]["rng_seed"] == expected
    assert captured["session"]["simulation_state"]["rng_seed"] == expected


def test_session_seed_cannot_change_after_first_persist(monkeypatch) -> None:
    session_id = "immutable-seed-session"
    seed = rng_seed_from_session_id(session_id)
    monkeypatch.setattr(
        session_service,
        "load_session_from_disk",
        lambda _session_id: {
            "session_id": session_id,
            "simulation_state": {"rng_seed": seed},
            "runtime_state": {},
        },
    )

    try:
        session_service.save_session(
            {
                "session_id": session_id,
                "simulation_state": {"rng_seed": seed + 1},
                "runtime_state": {},
            }
        )
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("changing the persisted RPG rng_seed must fail")


def test_turn_event_ids_are_stable_and_scoped_to_the_turn() -> None:
    event_id = deterministic_turn_uuid("session-7", 12, "combat_event", 2)

    assert event_id == deterministic_turn_uuid("session-7", 12, "combat_event", 2)
    assert event_id != deterministic_turn_uuid("session-7", 13, "combat_event", 2)


def test_event_bus_uses_uuid5_ids_inside_a_session_turn() -> None:
    session_id = "event-id-session"
    turn = 9
    context = TurnContext.capture(
        FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc)),
        session_seed=123,
        turn_index=turn,
        session_id=session_id,
    )
    bus = EventBus(
        clock=DeterministicClock(),
        determinism=DeterminismConfig(seed=123),
    )

    with bind_turn_context(context):
        bus.emit(Event(type="combat_event", payload={"damage": 4}))

    assert bus.history()[0].event_id == deterministic_turn_uuid(
        session_id,
        turn,
        "combat_event",
        0,
    )


def test_turn_clock_is_captured_once_and_text_rng_uses_recorded_turn_identity() -> None:
    initial = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    clock: Clock = FixedClock(initial)
    context = TurnContext.capture(clock, session_seed=44, turn_index=7)

    with bind_turn_context(context):
        timestamp = utc_now()
        first = rng_for_current_turn("text:test_choice").randint(0, 100000)
        second = rng_for_current_turn("text:test_choice").randint(0, 100000)

    assert timestamp == initial
    assert first == second
    assert clock.now_calls == 1


def test_text_rng_fails_closed_without_a_seeded_turn_context() -> None:
    try:
        rng_for_current_turn("text:test_choice")
    except RuntimeError as exc:
        assert "seeded RPG turn context" in str(exc)
    else:
        raise AssertionError("text RNG must require a seeded turn context")


def test_replay_turn_context_uses_recorded_time_without_reading_the_clock() -> None:
    recorded_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FixedClock(datetime(2030, 1, 1, tzinfo=timezone.utc))

    context = TurnContext.capture(
        clock,
        session_seed=44,
        turn_index=7,
        now=recorded_now,
    )

    assert context.now == recorded_now
    assert clock.now_calls == 0


def test_idle_replay_turn_time_comes_from_the_recorded_input() -> None:
    recorded_now = "2026-01-01T00:00:00+00:00"
    session = {
        "simulation_state": {"tick": 4},
        "runtime_state": {
            "mode": "replay",
            "llm_records_index": {"idle_tick:4": {"now": recorded_now}},
        },
    }

    now, error = recorded_idle_tick_time(session)

    assert error is None
    assert now == datetime.fromisoformat(recorded_now)


def test_political_system_uses_named_turn_streams(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr("app.apps.rpg.world.political_system.COUP_PROBABILITY", 1.0)
    faction = SimpleNamespace(
        id="mages_guild",
        name="Mages Guild",
        morale=0.0,
        relations={},
        adjust_relation=lambda *_args: None,
    )
    context = TurnContext.capture(
        FixedClock(datetime(2026, 9, 29, tzinfo=timezone.utc)),
        session_seed=66,
        turn_index=5,
        session_id="political-session",
    )

    with bind_turn_context(context):
        first = PoliticalSystem().update(SimpleNamespace(factions={faction.id: faction}))
        second = PoliticalSystem().update(SimpleNamespace(factions={faction.id: faction}))

    assert first == second
    assert first[0]["type"] == "coup"


def test_fifty_turn_replay_matches_each_state_hash() -> None:
    seed = 0x18F03A
    actions = tuple("attack_melee" if turn % 2 == 0 else "persuade" for turn in range(50))
    prompts = tuple([{"role": "user", "content": f"turn:{turn}"}] for turn in range(50))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    recorded_inputs = tuple(
        {"messages": prompt, "now": (start + timedelta(seconds=turn)).isoformat()}
        for turn, prompt in enumerate(prompts)
    )
    scripts = {
        prompt_digest(prompt): action
        for prompt, action in zip(prompts, actions, strict=True)
    }

    def play(inputs: tuple[dict[str, object], ...]) -> tuple[str, ...]:
        provider = FakeLLMProvider(scripts)
        simulation = {
            "player_state": {
                "stats": {"strength": 12, "dexterity": 10, "constitution": 10, "charisma": 12},
                "skills": {"swordsmanship": {"level": 2}, "persuasion": {"level": 2}},
                "inventory_state": {"equipment": {}},
            },
            "turn_history": [],
        }
        hashes: list[str] = []
        for turn, recorded_input in enumerate(inputs):
            now = datetime.fromisoformat(str(recorded_input["now"]))
            turn_context = TurnContext.capture(
                FixedClock(now),
                session_seed=seed,
                turn_index=turn,
            )
            with bind_turn_context(turn_context):
                prompt = recorded_input["messages"]
                response = provider.chat_completion(messages=prompt)
                action_type = response.content
                action = {
                    "action_type": action_type,
                    "target": {"id": "training_target", "name": "Training Target", "hp": 100, "stats": {"dexterity": 10, "constitution": 10}},
                }
                result = resolve_player_action(
                    simulation,
                    action,
                    rng_for_current_turn("player_action"),
                )
                simulation = result["simulation_state"]
                simulation["turn_index"] = turn + 1
                simulation["turn_history"].append(
                    {
                        "action": action,
                        "result": result["result"],
                        "recorded_now": utc_now().isoformat(),
                    }
                )
                hashes.append(hashlib.sha256(stable_json(simulation).encode("utf-8")).hexdigest())
        assert len(provider.calls) == 50
        return tuple(hashes)

    expected = play(recorded_inputs)
    replayed = play(recorded_inputs)
    assert expected == replayed
