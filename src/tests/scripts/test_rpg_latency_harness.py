"""RQ-0.5: the latency harness's per-class report and F1/F3 checks (no database, no model)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("omnix_rpg_latency_tests_target", ROOT / "scripts/rpg_latency_harness.py")
latency = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(latency)


def _row(complete, calls=0, first=None, known=None, model_ms=0.0, roles=()):
    return {"http": 200, "outcome_known_ms": known, "outcome_visible_ms": complete, "first_narration_ms": first,
            "complete_ms": complete, "model_calls": calls, "model_roles": list(roles), "model_ms": model_ms,
            "overhead_ms": complete - model_ms}


def test_every_roadmap_turn_class_is_measured():
    assert set(latency.CLASSES) == {"look", "arrive", "question", "buy", "fight", "tactical_move", "status", "wait"}
    assert {spec["scene"] for spec in latency.CLASSES.values()} <= set(latency.SCENE_SETUP)


def test_class_report_gives_p50_and_p95_and_counts_published_drafts():
    rows = [_row(float(ms), calls=1, first=ms / 2, known=ms / 4, model_ms=ms / 2, roles=("turn_narration",))
            for ms in range(100, 2100, 100)]
    rows[0]["first_narration_ms"] = None
    report = latency.class_report(rows)
    assert report["runs"] == 20 and report["first_narration_published"] == 19
    assert report["complete_ms"]["p50"] == 1000.0 and report["complete_ms"]["p95"] == 1900.0
    assert report["model_roles"] == ["turn_narration"]
    assert report["overhead_ms"]["p50"] == 500.0


def test_f3_checks_count_calls_per_turn():
    rows = {"look": [_row(10.0, calls=1), _row(10.0, calls=3)], "tactical_move": [_row(5.0, calls=1)]}
    classes = {name: latency.class_report(group) for name, group in rows.items()}
    checks = latency.checks(classes, rows)
    assert checks["F3_met"] is False
    assert checks["F3_max_calls_per_turn"] == 3
    assert checks["F3_deterministic_turns_with_a_call"] == 1
    # One revision of the narration is forgiven: its own call beyond the two.
    revised = _row(10.0, calls=3, roles=("semantic_intent", "narrative_writer", "narrative_writer"))
    rows = {"look": [_row(10.0, calls=2), revised], "tactical_move": [_row(5.0, calls=0)]}
    checks = latency.checks({name: latency.class_report(group) for name, group in rows.items()}, rows)
    assert checks["F3_met"] is True and checks["F3_turns_revised"] == 1
    assert checks["F3_max_calls_per_turn_but_a_revision"] == 2


def test_clock_marks_reset_per_turn():
    clock = latency.Clock()
    clock.resolve_done, clock.first_draft = 1.0, 2.0
    clock.reset()
    assert clock.resolve_done is None and clock.first_draft is None and clock.started > 0
    assert latency._ms(None, 1.0) is None and latency._ms(1.5, 1.0) == 500.0


def test_counting_provider_times_a_streamed_call_until_its_last_chunk(monkeypatch):
    from types import SimpleNamespace

    import itertools
    import time

    from tests.rehearsal.rpg.worlds import CountingProvider

    # A clock that moves 20 ms each time it is read stands in for real waiting.
    ticks = (index * 0.02 for index in itertools.count())
    monkeypatch.setattr(time, "perf_counter", lambda: next(ticks))

    class Inner:
        name = "fake"

        def chat_completion(self, messages, model=None, stream=False, **kwargs):
            def chunks():
                for text in ("a", "b"):
                    time.perf_counter()  # time passes while the chunk is written
                    yield SimpleNamespace(content=text, model="fake-model")
            return chunks() if stream else SimpleNamespace(content="ab", model="fake-model")

    counting = CountingProvider(Inner())
    message = SimpleNamespace(content="You are the Omnix RPG Narrative Writer.")
    assert [chunk.content for chunk in counting.chat_completion([message], stream=True)] == ["a", "b"]
    assert counting.calls[0]["role"] == "narrative_writer" and counting.calls[0]["ms"] >= 30
    counting.chat_completion([SimpleNamespace(content="other")])
    assert counting.calls[1]["role"] == "unscripted" and counting.resolved_models == {"fake-model"}
