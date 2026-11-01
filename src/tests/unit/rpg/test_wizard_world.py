"""The wizard's World Forge campaign plays from a world of the library (genesis/forge/wizard_world.py)."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from app.apps.rpg.genesis.forge.contract import CampaignGenesisContract
from app.apps.rpg.genesis.forge.wizard_world import APPROVED_BY, advance_wizard_world, wizard_world_id

CAMPAIGN = "rpg_wizard_1"


class _Library:
    """The library as the steps find it, and what they ask of it."""

    def __init__(self, *, world=None, review=None, runs=(), results=(), prepared=()) -> None:
        self.world, self.review, self.runs, self.results, self.prepared = world, review, list(runs), list(results), list(prepared)
        self.calls: list[tuple[str, dict]] = []

    def install(self, monkeypatch) -> None:
        library = self

        class _Work:
            world_scenarios = SimpleNamespace(get_world=lambda context, world_id: library.world)
            world_library = SimpleNamespace(list_generation_runs=lambda context, **kwargs: library.runs)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def rollback(self):
                pass

        def record(name, result=None):
            def call(*args, **kwargs):
                library.calls.append((name, {"args": args, **kwargs}))
                return result() if callable(result) else result
            return call

        monkeypatch.setattr(importlib.import_module("app.persistence.unit_of_work"), "unit_of_work",
                            lambda database=None: _Work())
        monkeypatch.setattr("app.security.tenant_context.current_tenant", lambda: object())
        worlds = "app.apps.rpg.genesis.worlds"
        monkeypatch.setattr(f"{worlds}.postgres_service.create_world_project", record("create"))
        monkeypatch.setattr(f"{worlds}.profile_authoring.read_world_profile_review",
                            lambda world_id, database=None: {"review": library.review})
        monkeypatch.setattr(f"{worlds}.profile_authoring.approve_world_profile_review", record("approve"))
        monkeypatch.setattr(f"{worlds}.library_service.start_world_library_generation", record("generate"))
        monkeypatch.setattr(f"{worlds}.library_service.read_world_generation",
                            lambda run_id, database=None, reconcile=True: {"run": library.runs[0],
                                                                           "topic_results": library.results})
        monkeypatch.setattr(f"{worlds}.library_service.publish_world_library_generation", record("publish"))
        monkeypatch.setattr(f"{worlds}.generation_acceptance.accept_world_generation_candidates", record("accept"))
        monkeypatch.setattr(f"{worlds}.launch_repair_service.prepare_opening_scenarios_for_launch",
                            record("prepare", lambda: {"prepared": library.prepared}))


def _contract() -> CampaignGenesisContract:
    return CampaignGenesisContract.model_validate({
        "campaign_template": "classic_fantasy", "genre": "frontier fantasy", "tone": "grim",
        "identity": {"name": "Wren"}, "world_options": {"starting_location": "old_mill", "seed": 9},
        "world_forge": {"enabled": True, "depth": "quick"}})


def _step(library, monkeypatch, launch=None):
    library.install(monkeypatch)
    return advance_wizard_world(_contract(), campaign_id=CAMPAIGN, launch=launch or (lambda opening: {"opened": opening}))


def test_the_steps_from_nothing_to_a_world_generating(monkeypatch) -> None:
    library = _Library()
    step = _step(library, monkeypatch)
    assert (step.stage, step.waiting, step.world_id) == ("world", True, wizard_world_id(CAMPAIGN))
    [(name, call)] = library.calls
    request = call["args"][0]
    assert name == "create" and request.world_id == "world:campaign:rpg_wizard_1" and request.title == "Wren's world"
    assert (request.genre, request.tone, request.seed) == ("frontier fantasy", "grim", 9)

    profiling = _Library(world={"id": "w"}, review={"status": "generating", "profile": {}})
    assert _step(profiling, monkeypatch).stage == "profile" and profiling.calls == []  # waits on the profile job

    reviewing = _Library(world={"id": "w"}, review={"status": "review_required", "profile": {"x": 1},
                                                    "profile_revision": 2})
    step = _step(reviewing, monkeypatch)
    [(name, call)] = reviewing.calls
    assert (step.stage, step.waiting, name) == ("profile", False, "approve")
    assert call["expected_profile_revision"] == 2 and call["approved_by"] == APPROVED_BY  # the player's approval

    approved = _Library(world={"id": "w"}, review={"status": "approved"})
    step = _step(approved, monkeypatch)
    [(name, call)] = approved.calls
    assert (step.stage, step.waiting, name, call["depth"]) == ("generating", True, "generate", "quick")


def test_generation_awaited_then_accepted_published_and_launched_from_the_named_opening(monkeypatch) -> None:
    running = _Library(world={"id": "w"}, review={"status": "approved"}, runs=[{"run_id": "r", "status": "running"}])
    assert _step(running, monkeypatch).waiting

    review = _Library(world={"id": "w"}, review={"status": "approved"}, runs=[{"run_id": "r", "status": "review"}],
                      results=[{"topic_id": "places", "status": "accepted"}, {"topic_id": "actors", "status": "ready"}])
    step = _step(review, monkeypatch)
    assert step.stage == "publishing" and [name for name, _ in review.calls] == ["accept", "publish"]
    assert review.calls[0][1]["topic_ids"] == ["actors"]  # only what was not yet accepted

    openings = [{"scenario_id": "scenario:gate", "title": "At the Gate",
                 "result": {"scenario_revision": {"document": {"starting_location_id": "location:gate"}}}},
                {"scenario_id": "scenario:mill", "title": "Dawn at the Old Mill",
                 "result": {"scenario_revision": {"document": {"starting_location_id": "location:old-mill"}}}}]
    ready = _Library(world={"id": "w"}, review={"status": "approved"}, runs=[{"run_id": "r", "status": "ready"}],
                     prepared=openings)
    step = _step(ready, monkeypatch)
    assert step.launched and step.detail["launch"]["opened"]["scenario_id"] == "scenario:mill"  # the wizard's place


def test_a_failed_generation_is_an_error_not_a_campaign_without_a_world(monkeypatch) -> None:
    failed = _Library(world={"id": "w"}, review={"status": "approved"}, runs=[{"run_id": "r", "status": "failed"}])
    with pytest.raises(ValueError, match="wizard_world_generation_failed"):
        _step(failed, monkeypatch)
