from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from app.jobs.models import ResourceClass
from app.rpg.session.genesis.async_coordinator import (
    CAMPAIGN_GENESIS_ASYNC_CONTRACT,
    CAMPAIGN_GENESIS_JOB_TYPE,
    CAMPAIGN_GENESIS_RESOURCE_CLASS,
    campaign_genesis_async_enabled,
    campaign_genesis_job_id,
    enqueue_campaign_genesis,
)
from app.rpg.session.genesis.contract import CampaignGenesisContract


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

    monkeypatch.setattr("app.rpg.session.service.save_session", save_session)
    monkeypatch.setattr(
        "app.persistence.identity_service.bootstrap_local_tenant",
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


def test_phase39_source_guards_cover_leases_recovery_and_restart_safe_commit() -> None:
    coordinator = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "async_coordinator.py"
    ).read_text(encoding="utf-8")
    pipeline = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "pipeline_adapter.py"
    ).read_text(encoding="utf-8")
    materialization = (
        ROOT
        / "src"
        / "app"
        / "rpg"
        / "session"
        / "genesis"
        / "materialization.py"
    ).read_text(encoding="utf-8")
    routes = (
        ROOT / "src" / "app" / "gateway" / "rpg_campaign_lore_routes.py"
    ).read_text(encoding="utf-8")

    assert "work.jobs.claim_next(" in coordinator
    assert "work.jobs.mark_running(" in coordinator
    assert "lease_seconds=_DEFAULT_LEASE_SECONDS" in coordinator
    assert "work.jobs.fail(" in coordinator
    assert "retry_delay_seconds=1" in coordinator
    assert 'status="generating" if retrying else "failed"' in coordinator
    assert "genesis_run_started=True" in coordinator
    assert "required=True" in coordinator
    assert "campaign_genesis_async_enabled()" in pipeline
    assert "enqueue_campaign_genesis(" in pipeline
    assert 'status="generating_world"' not in pipeline
    assert "campaign_bible_hash(bible)" in materialization
    assert "retry produced different canon" in materialization
    assert 'status="ready"' in materialization
    assert '@app.on_event("startup")' in routes
    assert "kick_campaign_genesis_worker()" in routes
