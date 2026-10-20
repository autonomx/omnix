"""Voice Studio Phase 7 over real PostgreSQL: client credentials, recipes, batch runs and watch folders."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL test database",
)


class _MemorySecrets:
    """A writable secret store for tests (the credential signing key lives here)."""

    name, writable = "memory", True

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)

    def names(self) -> list[str]:
        return sorted(self.values)


@pytest.fixture
def workspace():
    """An isolated workspace, installed as the tenant, with its database as the default and audit on."""
    from app.persistence import database as database_module
    from app.persistence.audit import PostgresAuditSink
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import PostgresIdentityRepository, ensure_local_identity
    from app.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.tenant_scope import system_scope
    from app.runtime.tenant_context import pop_tenant, push_tenant
    from app.security import audit

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=6))
    ensure_local_identity(database)
    seed = PostgresJobStoreAdapter(database)
    workspace_id = f"workspace:voice-phase7:{uuid.uuid4().hex}"
    with system_scope("identity.provision"), database.transaction() as connection:
        connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Voice test', %s)",
                           (workspace_id, seed.context.user_id))
        connection.execute(
            "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
            (f"membership:{uuid.uuid4().hex}", workspace_id, seed.context.user_id, ["owner", "admin", "member"]),
        )
        context = PostgresIdentityRepository(connection).load_context(user_id=seed.context.user_id,
                                                                      workspace_id=workspace_id)
    original = database_module.default_database
    database_module.default_database = lambda: database  # type: ignore[assignment]
    previous_sink = audit.audit_sink()
    audit.install_audit_sink(PostgresAuditSink(database))
    from app.security import secrets as secret_stores

    secret_stores.install_secret_store(_MemorySecrets())
    token = push_tenant(context)
    try:
        yield database, context
    finally:
        pop_tenant(token)
        secret_stores.install_secret_store(None)
        audit.install_audit_sink(previous_sink)
        database_module.default_database = original  # type: ignore[assignment]
        with system_scope("identity.provision"), database.transaction() as connection:
            connection.execute("DELETE FROM omnix_voice_watch_leases WHERE folder_id LIKE 'phase7-%%'")
            connection.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))
        database.close()


def _audits(database: Any, workspace_id: str, action: str) -> list[dict[str, Any]]:
    from app.persistence.tenant_scope import system_scope

    with system_scope("audit.write"), database.transaction() as connection:
        rows = connection.execute(
            "SELECT aggregate_id, payload FROM omnix_audit_events WHERE workspace_id = %s AND action = %s ORDER BY id",
            (workspace_id, action)).fetchall()
    return [{"target": row[0], **row[1]} for row in rows]


# --- client credentials ----------------------------------------------------------------------------


def test_a_credential_acts_in_its_workspace_and_only_within_its_grants(workspace,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform.voice import client_api

    database, context = workspace
    # Port bindings are installed by the gateway's composition; here the voice tools stand alone.
    monkeypatch.setattr(client_api, "registered_tools", lambda: {tool.name: tool for tool in client_api.voice_tools()})
    issued = client_api.issue_credential(name="Narration bot", capabilities=["voice.speak", "voice.list_voices"])
    assert issued["token"].startswith(client_api.TOKEN_PREFIX)
    assert all("token" not in item or item["token"] is None for item in client_api.list_credentials())
    credential, tenant = client_api.authenticate(issued["token"])
    assert tenant.workspace_id == context.workspace_id and tenant.user_id == context.user_id
    assert credential["capabilities"] == frozenset({"voice.speak", "voice.list_voices"})

    with pytest.raises(client_api.ClientCapabilityRefused, match="voice.design"):
        client_api.call_tool(credential, "design_voice", {"description": "a calm narrator"})
    refused = _audits(database, context.workspace_id, "voice.client.call")
    assert refused[-1]["target"] == "design_voice" and refused[-1]["outcome"] == "denied"
    assert refused[-1]["client_id"] == issued["id"]
    assert _audits(database, context.workspace_id, "voice.client.issue")[-1]["target"] == issued["id"]


def test_revoked_expired_and_altered_credentials_are_refused_and_audited(workspace) -> None:
    from app.platform.voice import client_api

    database, context = workspace
    revoked = client_api.issue_credential(name="Old bot", capabilities=["voice.speak"])
    assert client_api.revoke_credential(revoked["id"]) is True
    assert client_api.revoke_credential(revoked["id"]) is False
    with pytest.raises(client_api.ClientCredentialError, match="revoked"):
        client_api.authenticate(revoked["token"])

    altered = client_api.issue_credential(name="Bot", capabilities=["voice.speak"])
    expired = client_api.issue_credential(name="Short bot", capabilities=["voice.speak"])
    with database.transaction() as connection:
        connection.execute("UPDATE omnix_voice_client_credentials SET capabilities = %s WHERE id = %s",
                           (["voice.speak", "voice.design"], altered["id"]))
        connection.execute("UPDATE omnix_voice_client_credentials SET expires_at = clock_timestamp() - INTERVAL '1 minute' "
                           "WHERE id = %s", (expired["id"],))
    with pytest.raises(client_api.ClientCredentialError, match="altered"):
        client_api.authenticate(altered["token"])
    with pytest.raises(client_api.ClientCredentialError, match="expired"):
        client_api.authenticate(expired["token"])
    with pytest.raises(client_api.ClientCredentialError, match="unknown"):
        client_api.authenticate(client_api.TOKEN_PREFIX + "not-a-token")

    reasons = {(row["target"], row["reason"]) for row in _audits(database, context.workspace_id, "voice.client.call")
               if row["outcome"] == "denied"}
    assert reasons == {(revoked["id"], "revoked"), (altered["id"], "altered"), (expired["id"], "expired")}


def test_a_credential_signed_for_another_workspace_or_owner_is_refused(workspace) -> None:
    """The signature covers workspace and owner too, and is keyed outside PostgreSQL."""
    from app.platform.voice import client_api

    database, context = workspace
    issued = client_api.issue_credential(name="Bot", capabilities=["voice.speak"])
    with database.transaction() as connection:
        connection.execute("UPDATE omnix_voice_client_credentials SET expires_at = NULL WHERE id = %s", (issued["id"],))
    with pytest.raises(client_api.ClientCredentialError, match="altered"):
        client_api.authenticate(issued["token"])   # dropping the expiry voids it


def test_a_credential_stops_working_when_its_owner_is_no_longer_an_admin(workspace) -> None:
    from app.persistence.tenant_scope import system_scope
    from app.platform.voice import client_api

    database, context = workspace
    issued = client_api.issue_credential(name="Bot", capabilities=["voice.speak"])
    assert client_api.authenticate(issued["token"])[1].workspace_id == context.workspace_id
    with system_scope("identity.provision"), database.transaction() as connection:
        connection.execute("UPDATE omnix_workspace_memberships SET roles = %s WHERE workspace_id = %s",
                           (["member"], context.workspace_id))
    with pytest.raises(client_api.ClientCredentialError, match="no longer a workspace admin"):
        client_api.authenticate(issued["token"])


def test_only_admins_issue_credentials_and_grants_must_be_known(workspace) -> None:
    from app.platform.voice import client_api
    from app.runtime.tenant_context import TenantAccessDenied, pop_tenant, push_tenant

    _database, context = workspace
    with pytest.raises(ValueError, match="capabilities"):
        client_api.issue_credential(name="Bot", capabilities=["voice.clone"])
    member = context.__class__(user_id=context.user_id, workspace_id=context.workspace_id,
                               membership_id=context.membership_id, roles=frozenset({"member"}))
    token = push_tenant(member)
    try:
        with pytest.raises(TenantAccessDenied):
            client_api.issue_credential(name="Bot", capabilities=["voice.speak"])
    finally:
        pop_tenant(token)


# --- recipes and batches ---------------------------------------------------------------------------


def _audio(tmp_path: Path, name: str, content: bytes) -> str:
    from app.assets import AssetRecord, AssetType, default_asset_store

    path = tmp_path / f"{name}.wav"
    path.write_bytes(content)
    record = default_asset_store().upsert_asset(AssetRecord(
        id=f"audio:phase7-{uuid.uuid4().hex}", module="voice", type=AssetType.AUDIO, mime_type="audio/wav",
        storage_path=str(path), metadata={"title": name}, created_at=datetime.now(timezone.utc).isoformat()))
    return record.id


def test_asset_lineage_survives_the_postgresql_store(workspace, tmp_path: Path) -> None:
    """Stems and transcripts name their source (``parent_asset_ids``); an update without lineage keeps it."""
    from app.assets import AssetRecord, AssetType, default_asset_store

    store = default_asset_store()
    source = _audio(tmp_path, "source", b"RIFF-source")
    stem_path = tmp_path / "stem.wav"
    stem_path.write_bytes(b"RIFF-stem")
    stem = AssetRecord(id=f"audio:phase7-stem-{uuid.uuid4().hex}", module="voice", type=AssetType.AUDIO,
                       mime_type="audio/wav", storage_path=str(stem_path), metadata={"title": "Stem"},
                       parent_asset_ids=[source], compat={"contract": "test"},
                       created_at=datetime.now(timezone.utc).isoformat())
    created = store.upsert_asset(stem)
    assert created.parent_asset_ids == [source] and "parent_asset_ids" not in created.compat
    assert store.get_asset(stem.id).parent_asset_ids == [source]
    renamed = store.upsert_asset(stem.model_copy(update={"metadata": {"title": "Renamed"}, "parent_asset_ids": []}))
    assert renamed.metadata["title"] == "Renamed" and renamed.parent_asset_ids == [source]


def test_an_edited_transcript_is_saved_in_postgresql_and_a_stale_save_is_refused(workspace, tmp_path: Path) -> None:
    """The save route replaces the stored content (PostgreSQL keys content by blob, not by path)."""
    import json

    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.assets.content import read_asset_bytes
    from app.platform.voice.voice_studio_routes import register_voice_studio_routes

    document = {"schema": "omnix-transcript-v1", "language": "en", "duration": 2.0, "engine": "Parakeet-TDT",
                "diarized": False, "speakers": ["Speaker 1"], "text": "Hello there.", "source_asset_id": "",
                "segments": [{"start": 0.0, "end": 1.0, "speaker": "Speaker 1", "text": "Hello there.",
                              "words": [{"start": 0.0, "end": 0.5, "word": "Hello", "confidence": 0.9},
                                        {"start": 0.5, "end": 1.0, "word": "there.", "confidence": 0.9}]}]}
    first = tmp_path / "t.json"
    first.write_text(json.dumps(document), encoding="utf-8")
    store = default_asset_store()
    asset = store.upsert_asset(AssetRecord(
        id=f"transcript:phase7-{uuid.uuid4().hex}", module="stt", type=AssetType.TRANSCRIPT,
        mime_type="application/json", storage_path=str(first), metadata={"title": "Call", "revision": 1},
        created_at=datetime.now(timezone.utc).isoformat()))
    router = APIRouter()
    register_voice_studio_routes(router, SimpleNamespace())
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    edited = {**document, "segments": [{**document["segments"][0], "words": [
        {"start": 0.0, "end": 0.5, "word": "Hullo", "confidence": 1.0},
        {"start": 0.5, "end": 1.0, "word": "there.", "confidence": 0.9}]}]}
    saved = client.put(f"/api/voice/transcripts/{asset.id}", json={"document": edited, "expected_revision": 1})
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    stored = json.loads(read_asset_bytes(store.get_asset(asset.id), max_bytes=100_000))
    assert stored["text"] == "Hullo there."
    assert client.get(f"/api/voice/transcripts/{asset.id}").json()["document"]["text"] == "Hullo there."
    stale = client.put(f"/api/voice/transcripts/{asset.id}", json={"document": edited, "expected_revision": 1})
    assert stale.status_code == 409


def test_two_saves_of_one_transcript_revision_leave_the_winner_readable(workspace, tmp_path: Path) -> None:
    """The losing save of a revision race deletes only its own content, never the winner's."""
    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.assets.content import read_asset_bytes

    store = default_asset_store()
    first = tmp_path / "t.json"
    first.write_text('{"v": 1}', encoding="utf-8")
    asset = store.upsert_asset(AssetRecord(
        id=f"transcript:phase7-race-{uuid.uuid4().hex}", module="stt", type=AssetType.TRANSCRIPT,
        mime_type="application/json", storage_path=str(first), metadata={"revision": 1},
        created_at=datetime.now(timezone.utc).isoformat()))
    winner, loser = tmp_path / "a" / "t-r2.json", tmp_path / "b" / "t-r2.json"   # the same name, as the route makes
    for path, body in ((winner, '{"v": "winner"}'), (loser, '{"v": "loser"}')):
        path.parent.mkdir()
        path.write_text(body, encoding="utf-8")
    assert store.replace_content(asset.id, winner, metadata={"revision": 2}, expected_revision=1) is not None
    assert store.replace_content(asset.id, loser, metadata={"revision": 2}, expected_revision=1) is None
    assert read_asset_bytes(store.get_asset(asset.id), max_bytes=1000) == b'{"v": "winner"}'


class _Jobs:
    """A job store whose jobs finish when the test says so."""

    def __init__(self) -> None:
        self.jobs: dict[str, Any] = {}

    def create_job(self, request: Any) -> Any:
        job = SimpleNamespace(id=f"job:{uuid.uuid4().hex}", type=request.type, status="queued", output_refs=[],
                              error=None, request=request)
        self.jobs[job.id] = job
        return job

    def create_job_once(self, request: Any, *, idempotency_key: str) -> Any:
        """Like the PostgreSQL store: the same key returns the same job."""
        job_id = f"job:once:{idempotency_key}"
        if job_id not in self.jobs:
            self.jobs[job_id] = SimpleNamespace(id=job_id, type=request.type, status="queued", output_refs=[],
                                                error=None, request=request)
        return self.jobs[job_id]

    def get_job(self, job_id: str) -> Any:
        return self.jobs.get(job_id)

    def finish(self, *, fail: bool = False, retryable: bool = True) -> None:
        for job in self.jobs.values():
            if job.status != "queued":
                continue
            if fail:
                job.status, job.error = "failed", SimpleNamespace(message="engine crashed", retryable=retryable)
            else:
                job.status = "completed"
                job.output_refs = [{"type": "audio", "kind": "stem_vocals", "asset_id": f"audio:out-{job.id}"}]


def test_recipe_versions_change_only_when_their_steps_do(workspace) -> None:
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    assert recipe["version"] == 1
    renamed = automation.save_recipe(name="Clean up", steps=[{"tool": "isolate"}], recipe_id=recipe["id"])
    assert renamed["version"] == 1 and renamed["name"] == "Clean up"
    changed = automation.save_recipe(name="Clean up", steps=[{"tool": "isolate"}, {"tool": "enhance"}],
                                     recipe_id=recipe["id"])
    assert changed["version"] == 2
    with pytest.raises(automation.AutomationNotFound):
        automation.save_recipe(name="X", steps=[{"tool": "isolate"}], recipe_id="vrecipe:missing")


def test_a_batch_steps_each_item_through_the_recipe_and_retries_failures(workspace, tmp_path: Path) -> None:
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}, {"tool": "enhance"}])
    inputs = [_audio(tmp_path, f"take{index}", f"RIFF-{index}".encode()) for index in range(6)]
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=inputs)
    assert run["counts"] == {"pending": 6}
    jobs = _Jobs()
    advancer = automation.BatchAdvancer(job_store_factory=lambda: jobs)

    assert advancer.advance(run["id"])["submitted"] == automation.ACTIVE_PER_RUN  # a run never floods the queue
    assert {job.type for job in jobs.jobs.values()} == {"audio.isolate"}
    assert all(job.request.resource_class.value == "gpu:audio" for job in jobs.jobs.values())
    jobs.finish()
    moved = advancer.advance(run["id"])
    assert moved["submitted"] == automation.ACTIVE_PER_RUN
    # Enhance takes the stem isolate made, not the source.
    enhance = [job for job in jobs.jobs.values() if job.type == "audio.enhance"]
    assert enhance and all(job.request.input_ref["asset_id"].startswith("audio:out-") for job in enhance)

    jobs.finish(fail=True)  # every in-flight job fails once: retried
    assert advancer.advance(run["id"])["retried"] == automation.ACTIVE_PER_RUN
    for _ in range(10):
        jobs.finish()
        advancer.advance(run["id"])
    finished = automation.get_run(run["id"])
    assert finished["status"] == "done" and finished["counts"] == {"done": 6}
    assert all([output["tool"] for output in item["outputs"]] == ["isolate", "enhance"] for item in finished["items"])


def test_two_advancers_never_submit_or_move_an_item_twice(workspace, tmp_path: Path) -> None:
    """Every job-worker process runs an advancer; one ticking inside another's submission changes nothing."""
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}, {"tool": "enhance"}])
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=[_audio(tmp_path, "a", b"RIFF-a")])
    jobs = _Jobs()
    other = automation.BatchAdvancer(job_store_factory=lambda: jobs)
    original = jobs.create_job_once
    nested = {"done": False}

    def create_job_once(request: Any, *, idempotency_key: str) -> Any:
        job = original(request, idempotency_key=idempotency_key)
        if not nested["done"]:
            nested["done"] = True
            other.advance(run["id"])  # the other process, between this one's submission and its record
        return job

    jobs.create_job_once = create_job_once  # type: ignore[method-assign]
    automation.BatchAdvancer(job_store_factory=lambda: jobs).advance(run["id"])
    assert len(jobs.jobs) == 1
    assert automation.get_run(run["id"])["items"][0]["job_id"] == next(iter(jobs.jobs))

    jobs.finish()
    automation.BatchAdvancer(job_store_factory=lambda: jobs).advance(run["id"])
    automation.BatchAdvancer(job_store_factory=lambda: jobs).advance(run["id"])  # sees the item already moved on
    assert [job.type for job in jobs.jobs.values()].count("audio.enhance") == 1


def test_a_cancelled_or_vanished_job_settles_its_item(workspace, tmp_path: Path) -> None:
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=[_audio(tmp_path, "a", b"RIFF-a"),
                                                                      _audio(tmp_path, "b", b"RIFF-b")])
    jobs = _Jobs()
    advancer = automation.BatchAdvancer(job_store_factory=lambda: jobs)
    advancer.advance(run["id"])
    cancelled, vanished = list(jobs.jobs)
    jobs.jobs[cancelled].status = "canceled"  # JobStatus.CANCELED: a person stopped it, so no retry
    del jobs.jobs[vanished]
    advancer.advance(run["id"])
    settled = {item["error"]: item for item in automation.get_run(run["id"])["items"]}
    assert settled["canceled"]["status"] == "failed"
    # The vanished job's item is retried with a fresh job.
    assert settled["the job is gone"]["status"] == "running" and settled["the job is gone"]["attempts"] == 1


def test_a_failure_that_cannot_be_retried_fails_only_its_item(workspace, tmp_path: Path) -> None:
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=[_audio(tmp_path, "a", b"RIFF-a")])
    jobs = _Jobs()
    advancer = automation.BatchAdvancer(job_store_factory=lambda: jobs)
    advancer.advance(run["id"])
    jobs.finish(fail=True, retryable=False)
    assert advancer.advance(run["id"])["failed"] == 1
    failed = automation.get_run(run["id"])
    assert failed["status"] == "failed" and failed["items"][0]["error"] == "engine crashed"


def test_a_rerun_skips_inputs_done_at_this_recipe_version(workspace, tmp_path: Path) -> None:
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    first = _audio(tmp_path, "first", b"RIFF-same")
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=[first])
    jobs = _Jobs()
    advancer = automation.BatchAdvancer(job_store_factory=lambda: jobs)
    advancer.advance(run["id"])
    jobs.finish()
    advancer.advance(run["id"])
    # The same content under another name: skipped with the earlier outputs. New content: run.
    again = automation.start_batch(recipe_id=recipe["id"], asset_ids=[_audio(tmp_path, "copy", b"RIFF-same"),
                                                                        _audio(tmp_path, "new", b"RIFF-new")])
    assert [item["status"] for item in again["items"]] == ["skipped", "pending"]
    assert again["items"][0]["outputs"][0]["tool"] == "isolate"
    automation.save_recipe(name="Clean", steps=[{"tool": "isolate", "settings": {"model": "demucs"}}],
                           recipe_id=recipe["id"])
    changed = automation.start_batch(recipe_id=recipe["id"], asset_ids=[first])
    assert changed["items"][0]["status"] == "pending"  # a new recipe version runs again


def test_a_run_whose_owner_left_the_workspace_stops(workspace, tmp_path: Path) -> None:
    from app.persistence.tenant_scope import system_scope
    from app.platform.voice import automation

    database, context = workspace
    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=[_audio(tmp_path, "a", b"RIFF-a")])
    with system_scope("identity.provision"), database.transaction() as connection:
        connection.execute("DELETE FROM omnix_workspace_memberships WHERE workspace_id = %s AND user_id = %s",
                           (context.workspace_id, context.user_id))
    jobs = _Jobs()
    automation.BatchAdvancer(job_store_factory=lambda: jobs).tick()
    stopped = automation.get_run(run["id"])
    assert stopped["status"] == "failed" and jobs.jobs == {}
    assert "no longer a member" in stopped["items"][0]["error"]


def test_cancelling_a_batch_fails_its_pending_items(workspace, tmp_path: Path) -> None:
    from app.platform.voice import automation

    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    run = automation.start_batch(recipe_id=recipe["id"], asset_ids=[_audio(tmp_path, "a", b"RIFF-a")])
    cancelled = automation.cancel_run(run["id"])
    assert cancelled["status"] == "cancelled" and cancelled["items"][0]["error"] == "cancelled"
    assert automation.BatchAdvancer(job_store_factory=_Jobs).tick() == {}  # nothing running to advance


# --- watch folders ----------------------------------------------------------------------------------


def test_one_holder_at_a_time_takes_a_watch_folder(workspace) -> None:
    from app.platform.voice.watch_folders import take_lease

    folder = f"phase7-{uuid.uuid4().hex[:8]}"
    first = take_lease(folder, "host-a", seconds=5)
    assert first is not None
    assert take_lease(folder, "host-b", seconds=5) is None
    assert take_lease(folder, "host-a", seconds=5) == first  # renewing keeps the fence


def _folder(tmp_path: Path, context: Any, recipe_id: str) -> Any:
    from app.platform.voice.watch_folders import WatchFolder

    (tmp_path / "in" / "day1").mkdir(parents=True)
    (tmp_path / "out").mkdir()
    return WatchFolder.from_entry({"id": f"phase7-{uuid.uuid4().hex[:8]}", "path": str(tmp_path / "in"),
                                   "output": str(tmp_path / "out"), "recipe_id": recipe_id,
                                   "workspace_id": context.workspace_id, "owner_user_id": context.user_id})


def _settle(watcher: Any, folder: Any, monkeypatch: pytest.MonkeyPatch) -> int:
    """Two scans with the files older than the settle time: the second takes them."""
    from app.platform.voice import watch_folders

    monkeypatch.setattr(watch_folders, "STABLE_SECONDS", 0.0)
    watcher.scan(folder)
    return watcher.scan(folder)


def test_a_watch_folder_takes_each_file_once_across_restarts(workspace, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform.voice import automation
    from app.platform.voice.watch_folders import WatchFolders

    database, context = workspace
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path / "data")
    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    folder = _folder(tmp_path, context, recipe["id"])
    (folder.input / "day1" / "talk.wav").write_bytes(b"RIFF-talk")
    (folder.input / "notes.txt").write_text("not audio")
    first = WatchFolders([folder])
    assert _settle(first, folder, monkeypatch) == 1
    # A second worker, and the same worker after a restart, see the ledger: nothing is taken twice.
    assert _settle(WatchFolders([folder]), folder, monkeypatch) == 0
    assert first.scan(folder) == 0
    runs = [run for run in automation.list_runs() if run["watch_folder"] == folder.id]
    assert len(runs) == 1
    run = automation.get_run(runs[0]["id"])
    assert [item["output_name"] for item in run["items"]] == ["day1/talk.wav"]

    # Changed content at the same path is a new file.
    time.sleep(0.01)
    (folder.input / "day1" / "talk.wav").write_bytes(b"RIFF-talk-v2")
    assert _settle(WatchFolders([folder]), folder, monkeypatch) == 1


def test_a_finished_watch_item_writes_its_outputs_beside_its_name(workspace, tmp_path: Path,
                                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform.voice import automation
    from app.platform.voice.watch_folders import WatchFolders

    _database, context = workspace
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path / "data")
    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    folder = _folder(tmp_path, context, recipe["id"])
    (folder.input / "day1" / "talk.wav").write_bytes(b"RIFF-talk")
    watcher = WatchFolders([folder])
    _settle(watcher, folder, monkeypatch)
    run = next(run for run in automation.list_runs() if run["watch_folder"] == folder.id)
    stem = _audio(tmp_path, "stem", b"RIFF-vocals")

    jobs = _Jobs()
    advancer = automation.BatchAdvancer(job_store_factory=lambda: jobs, on_item_done=watcher.deliver)
    advancer.advance(run["id"])
    for job in jobs.jobs.values():
        job.status, job.output_refs = "completed", [{"type": "audio", "kind": "stem_vocals", "asset_id": stem}]
    advancer.advance(run["id"])
    assert (folder.output / "day1" / "talk.vocals.wav").read_bytes() == b"RIFF-vocals"


def test_a_claim_retaken_after_a_crash_reuses_the_batch_it_started(workspace, tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """A crash between starting the batch and recording it in the ledger never processes the file twice."""
    from app.platform.voice import automation, watch_folders
    from app.platform.voice.watch_folders import WatchFolders

    database, context = workspace
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path / "data")
    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    folder = _folder(tmp_path, context, recipe["id"])
    (folder.input / "day1" / "talk.wav").write_bytes(b"RIFF-talk")
    crashing = WatchFolders([folder])

    def crash(*_args: Any) -> None:
        raise RuntimeError("worker killed")

    monkeypatch.setattr(crashing, "_record", crash)
    with pytest.raises(RuntimeError):
        _settle(crashing, folder, monkeypatch)
    with database.transaction() as connection:   # the claim is old enough to be retaken
        connection.execute("UPDATE omnix_voice_watch_items SET created_at = created_at - INTERVAL '1 hour' "
                           "WHERE folder_id = %s", (folder.id,))
    monkeypatch.setattr(watch_folders, "RECLAIM_AFTER_SECONDS", 60.0)
    assert _settle(WatchFolders([folder]), folder, monkeypatch) == 0
    assert len([run for run in automation.list_runs() if run["watch_folder"] == folder.id]) == 1
    with database.transaction() as connection:
        recorded = connection.execute("SELECT batch_item_id FROM omnix_voice_watch_items WHERE folder_id = %s",
                                      (folder.id,)).fetchone()[0]
    assert recorded.startswith("vbitem:")


def test_identical_files_at_two_paths_are_two_inputs(workspace, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform.voice import automation
    from app.platform.voice.watch_folders import WatchFolders

    _database, context = workspace
    monkeypatch.setattr("app.runtime.paths.resources_data_root", lambda: tmp_path / "data")
    recipe = automation.save_recipe(name="Clean", steps=[{"tool": "isolate"}])
    folder = _folder(tmp_path, context, recipe["id"])
    (folder.input / "day1" / "a.wav").write_bytes(b"RIFF-same")
    (folder.input / "day1" / "b.wav").write_bytes(b"RIFF-same")
    assert _settle(WatchFolders([folder]), folder, monkeypatch) == 2
    run = next(run for run in automation.list_runs() if run["watch_folder"] == folder.id)
    assert sorted(item["output_name"] for item in automation.get_run(run["id"])["items"]) == ["day1/a.wav",
                                                                                              "day1/b.wav"]
