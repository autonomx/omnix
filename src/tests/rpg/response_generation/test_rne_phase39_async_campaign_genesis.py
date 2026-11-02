from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from app.jobs.models import ResourceClass
from app.apps.rpg.genesis.forge.async_coordinator import (
    CAMPAIGN_GENESIS_ASYNC_CONTRACT,
    CAMPAIGN_GENESIS_JOB_TYPE,
    CAMPAIGN_GENESIS_RESOURCE_CLASS,
    campaign_genesis_async_enabled,
    campaign_genesis_job_id,
    campaign_genesis_sync_fallback_allowed,
    enqueue_campaign_genesis,
    run_campaign_genesis_worker_once,
)
from app.apps.rpg.genesis.forge.contract import CampaignGenesisContract
from app.apps.rpg.session.service import SESSION_CAMPAIGN_SESSIONS


ROOT = Path(__file__).resolve().parents[4]


def _contract() -> CampaignGenesisContract:
    return CampaignGenesisContract.model_validate(
        {
            "campaign_template": "classic_fantasy",
            "genre": "fantasy",
            "tone": "grounded adventure",
            "world_options": {
                "starting_location": "rusty_flagon_tavern",
                "difficulty": "normal",
                "world_activity": "living_world",
                "economy_pressure": "normal",
                "combat_lethality": "normal",
                "seed": 39,
            },
            "world_forge": {
                "enabled": True,
                "depth": "quick",
                "background_expansion": False,
                "require_consistency_audit": True,
                "require_opening_dossiers": True,
            },
        }
    )


class _Campaigns:
    def __init__(self) -> None:
        self.created: dict | None = None

    def get_campaign(self, context, campaign_id, *, for_update=False):
        return None

    def create_campaign(self, context, **payload):
        self.created = dict(payload)
        return {"id": payload["campaign_id"], "revision": 0}


class _Jobs:
    def __init__(self) -> None:
        self.created: dict | None = None

    def get_job(self, context, job_id):
        return None

    def create_job(self, context, payload):
        self.created = dict(payload)
        return {
            "id": payload["id"],
            "job_type": payload["job_type"],
            "status": "queued",
        }


class _Genesis:
    def __init__(self) -> None:
        self.started: dict | None = None

    def start(self, context, **payload):
        self.started = dict(payload)
        return {"status": "planned", **payload}


class _Work:
    def __init__(self) -> None:
        self.rpg = _Campaigns()
        self.jobs = _Jobs()
        self.campaign_genesis = _Genesis()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.committed = True


def _prepared_result() -> dict:
    return {
        "ok": True,
        "session_id": "campaign:phase39",
        "status": "generating_world",
        "session": {
            "manifest": {
                "session_id": "campaign:phase39",
                "schema_version": "rpg-session-v1",
            },
            "state": {"title": "Phase 39"},
            "runtime_state": {},
            "setup_payload": {},
        },
        "game": {"title": "Phase 39"},
    }


def test_async_mode_is_production_default_but_deterministic_ci_is_explicit() -> None:
    assert campaign_genesis_async_enabled(
        {"OMNIX_RPG_CAMPAIGN_GENESIS_MODE": "async"}
    ) is True
    assert campaign_genesis_async_enabled({"RPG_TEST_MODE": "deterministic"}) is False
    assert campaign_genesis_async_enabled(
        {
            "RPG_TEST_MODE": "deterministic",
            "OMNIX_RPG_CAMPAIGN_GENESIS_MODE": "async",
        }
    ) is True
    assert campaign_genesis_async_enabled(
        {"OMNIX_RPG_CAMPAIGN_GENESIS_MODE": "sync"}
    ) is False
    assert campaign_genesis_sync_fallback_allowed({}) is True
    assert campaign_genesis_sync_fallback_allowed(
        {"OMNIX_RPG_CAMPAIGN_GENESIS_MODE": "async"}
    ) is False


def test_world_forge_without_the_queue_is_refused_not_played_without_a_world(monkeypatch) -> None:
    """The campaign's world is made in the library by the genesis job; with no durable queue there is no world to
    make, so the request is refused (roadmap §4.4: every campaign plays from a world)."""
    pipeline = importlib.import_module("app.apps.rpg.genesis.forge.pipeline_adapter")
    contract = _contract()
    monkeypatch.setattr(pipeline, "compile_campaign_genesis", lambda value: {"compiled": True})
    monkeypatch.setattr(pipeline, "bootstrap_session_from_compiled_genesis", lambda value: {"bootstrap": True})
    monkeypatch.setattr(pipeline, "adapt_genesis_payload_to_new_game_payload", lambda value: {"legacy": True})
    monkeypatch.setattr(pipeline, "prepare_new_game_session_from_compiled_genesis", lambda **kwargs: _prepared_result())
    monkeypatch.setattr("app.apps.rpg.genesis.forge.async_coordinator.campaign_genesis_async_enabled", lambda: True)
    monkeypatch.setattr("app.apps.rpg.genesis.forge.async_coordinator.campaign_genesis_sync_fallback_allowed",
                        lambda: True)
    monkeypatch.setattr("app.apps.rpg.genesis.forge.async_coordinator.enqueue_campaign_genesis",
                        lambda *args, **kwargs: {"ok": False, "error": "campaign_genesis_enqueue_failed",
                                                 "detail": "PostgreSQL unavailable"})

    result = pipeline.create_new_game_from_genesis_payload({"genesis": contract.model_dump(mode="json")},
                                                           sessions=SESSION_CAMPAIGN_SESSIONS)

    assert result["ok"] is False and result["error"] == "campaign_world_forge_requires_queue"


def test_campaign_genesis_resource_class_is_part_of_the_shared_job_contract() -> None:
    assert ResourceClass(CAMPAIGN_GENESIS_RESOURCE_CLASS) is (
        ResourceClass.RPG_CAMPAIGN_GENESIS
    )


def test_enqueue_persists_blocked_shell_and_one_durable_job(monkeypatch) -> None:
    work = _Work()
    saved: list[dict] = []

    def save_session(session, *, compact=False):
        saved.append(session)
        return session

    monkeypatch.setattr("app.apps.rpg.session.service.save_session", save_session)
    monkeypatch.setattr(
        "app.persistence.identity_service.ensure_local_identity",
        lambda database: SimpleNamespace(workspace_id="workspace", user_id="user"),
    )
    unit_of_work_module = importlib.import_module("app.persistence.unit_of_work")
    monkeypatch.setattr(unit_of_work_module, "unit_of_work", lambda database: work)

    contract = _contract()
    compiled = {
        "compiled_world_forge": {
            "topic_graph": {
                "graph_version": "rpg_campaign_topic_graph_v1",
                "nodes": [],
            }
        }
    }
    result = enqueue_campaign_genesis(
        _prepared_result(),
        contract=contract,
        compiled=compiled,
        bootstrap={"active_goals": []},
        legacy={"campaign_template": "classic_fantasy"},
        database=object(),
        kick_worker=False,
        sessions=SESSION_CAMPAIGN_SESSIONS,
    )

    job_id = campaign_genesis_job_id("campaign:phase39")
    assert result["ok"] is True
    assert result["status"] == "generating_world"
    assert result["creation_job"]["id"] == job_id
    runtime = result["session"]["runtime_state"]
    assert runtime["active_job_id"] == job_id
    assert runtime["campaign_launch_gate"]["ready"] is False
    assert runtime["campaign_generation"]["contract_version"] == (
        CAMPAIGN_GENESIS_ASYNC_CONTRACT
    )
    assert saved and saved[-1]["manifest"]["creation_status"] == "queued"
    assert work.committed is True
    assert work.campaign_genesis.started is not None
    assert work.campaign_genesis.started["campaign_id"] == "campaign:phase39"
    assert work.jobs.created is not None
    assert work.jobs.created["id"] == job_id
    assert work.jobs.created["job_type"] == CAMPAIGN_GENESIS_JOB_TYPE
    assert work.jobs.created["resource_class"] == CAMPAIGN_GENESIS_RESOURCE_CLASS
    payload = work.jobs.created["input_payload"]
    assert payload["campaign_id"] == "campaign:phase39"
    assert payload["contract"]["world_options"]["seed"] == 39
    assert payload["compiled"] == compiled


def test_enqueue_normalizes_database_bootstrap_failure(monkeypatch) -> None:
    saved: dict[str, dict] = {}

    def save_session(session, *, compact=False):
        campaign_id = session["manifest"]["session_id"]
        saved[campaign_id] = session
        return session

    monkeypatch.setattr("app.apps.rpg.session.service.save_session", save_session)
    monkeypatch.setattr(
        "app.apps.rpg.session.service.load_session",
        lambda campaign_id: saved.get(campaign_id),
    )
    monkeypatch.setattr(
        "app.apps.rpg.genesis.forge.async_coordinator._database",
        lambda value: (_ for _ in ()).throw(RuntimeError("PostgreSQL driver unavailable")),
    )

    result = enqueue_campaign_genesis(
        _prepared_result(),
        contract=_contract(),
        compiled={"compiled_world_forge": {"topic_graph": {}}},
        bootstrap={},
        legacy={},
        kick_worker=False,
        sessions=SESSION_CAMPAIGN_SESSIONS,
    )

    assert result["ok"] is False
    assert result["error"] == "campaign_genesis_enqueue_failed"
    assert result["detail"] == "PostgreSQL driver unavailable"
    assert result["creation_progress"]["status"] == "failed"
    assert result["creation_progress"]["progress"] == 0
    assert result["session"]["runtime_state"]["campaign_generation"]["stage"] == "enqueue_failed"


class _WorkerJobs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def claim_next(self, context, **kwargs):
        return {"id": "rpg-genesis:campaign:phase39", "job_type": CAMPAIGN_GENESIS_JOB_TYPE, "lease_token": "t",
                "input_payload": {"campaign_id": "campaign:phase39", "contract": _contract().model_dump(mode="json")}}

    def mark_running(self, context, **kwargs):
        return self.claim_next(context)

    def defer(self, context, **kwargs):
        self.calls.append(("defer", kwargs))
        return {"status": "queued"}

    def complete(self, context, **kwargs):
        self.calls.append(("complete", kwargs))
        return {"status": "completed"}


class _WorkerGenesis:
    def __init__(self) -> None:
        self.progress: list[dict] = []

    def update(self, context, **kwargs):
        self.progress.append(dict(kwargs))


def _worker(monkeypatch, step) -> tuple[dict, _WorkerJobs, _WorkerGenesis]:
    unit_of_work_module = importlib.import_module("app.persistence.unit_of_work")

    work = _Work()
    work.jobs = _WorkerJobs()
    work.campaign_genesis = _WorkerGenesis()
    work.rollback = lambda: None
    monkeypatch.setattr(unit_of_work_module, "unit_of_work", lambda database=None: work)
    monkeypatch.setattr("app.apps.rpg.genesis.forge.async_coordinator._write_session_progress",
                        lambda *args, **kwargs: None)
    monkeypatch.setattr("app.apps.rpg.genesis.forge.wizard_world.advance_wizard_world",
                        lambda contract, **kwargs: step)
    sessions = SimpleNamespace(load=lambda campaign_id: {"manifest": {"session_id": campaign_id}})
    return run_campaign_genesis_worker_once(sessions=sessions, database=object()), work.jobs, work.campaign_genesis


def test_the_genesis_job_takes_a_step_of_the_world_and_waits_on_the_librarys_workers(monkeypatch) -> None:
    from app.apps.rpg.genesis.forge.async_coordinator import WIZARD_WORLD_POLL_SECONDS
    from app.apps.rpg.genesis.forge.wizard_world import WizardWorldStep

    result, jobs, genesis = _worker(monkeypatch, WizardWorldStep("generating", waiting=True, world_id="world:x"))
    assert result["status"] == "generating" and result["stage"] == "generating"
    [(kind, deferred)] = jobs.calls
    assert kind == "defer" and deferred["delay_seconds"] == WIZARD_WORLD_POLL_SECONDS  # without spending an attempt
    assert genesis.progress[-1]["progress"]["stage"] == "world_generating"
    _, jobs, _ = _worker(monkeypatch, WizardWorldStep("publishing", world_id="world:x"))
    assert jobs.calls[0][1]["delay_seconds"] == 1  # a step done, not waiting: straight on to the next


def test_the_genesis_job_is_complete_when_the_campaign_has_set_out_from_its_world(monkeypatch) -> None:
    from app.apps.rpg.genesis.forge.wizard_world import WizardWorldStep

    launched = WizardWorldStep("launched", world_id="world:x", detail={"launch": {"session": {"state": {}}}})
    result, jobs, genesis = _worker(monkeypatch, launched)
    assert result["status"] == "ready" and result["world_id"] == "world:x"
    assert [kind for kind, _ in jobs.calls] == ["complete"]
    assert genesis.progress[-1]["status"] == "ready"
