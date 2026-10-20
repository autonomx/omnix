"""Voice Studio Phase 1 over real PostgreSQL: deferral, swap coordination, scripts and takes."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="requires disposable PostgreSQL test database",
)


@pytest.fixture
def workspace():
    """An isolated workspace, installed as the tenant, with its database as the default."""
    from app.persistence import database as database_module
    from app.persistence.config import DatabaseSettings
    from app.persistence.database import PostgresDatabase
    from app.persistence.identity_service import PostgresIdentityRepository, ensure_local_identity
    from app.persistence.job_store import PostgresJobStoreAdapter
    from app.persistence.tenant_scope import system_scope
    from app.runtime.tenant_context import pop_tenant, push_tenant

    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_max=6))
    ensure_local_identity(database)
    seed = PostgresJobStoreAdapter(database)
    workspace_id = f"workspace:voice-phase1:{uuid.uuid4().hex}"
    with system_scope("identity.provision"), database.transaction() as connection:
        connection.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, 'Voice test', %s)",
                           (workspace_id, seed.context.user_id))
        connection.execute(
            "INSERT INTO omnix_workspace_memberships (id, workspace_id, user_id, roles) VALUES (%s, %s, %s, %s)",
            (f"membership:{uuid.uuid4().hex}", workspace_id, seed.context.user_id, ["owner", "admin", "member"]),
        )
        context = PostgresIdentityRepository(connection).load_context(user_id=seed.context.user_id, workspace_id=workspace_id)
    original = database_module.default_database
    database_module.default_database = lambda: database  # type: ignore[assignment]
    token = push_tenant(context)
    store = PostgresJobStoreAdapter(database, context=context)
    _reset_swap_tables(database)
    try:
        yield database, store
    finally:
        _reset_swap_tables(database)
        pop_tenant(token)
        database_module.default_database = original  # type: ignore[assignment]
        with system_scope("identity.provision"), database.transaction() as connection:
            connection.execute("DELETE FROM omnix_workspaces WHERE id = %s", (workspace_id,))
        database.close()


def _reset_swap_tables(database: Any) -> None:
    with database.transaction() as connection:
        connection.execute("DELETE FROM omnix_tts_swap_requests")
        connection.execute("DELETE FROM omnix_tts_live_sessions")
        connection.execute(
            """UPDATE omnix_tts_swap_state SET phase = 'idle', holder_id = NULL, engine = NULL, restore_engine = NULL,
                      lease_expires_at = NULL, group_started_at = NULL, interrupted = FALSE, detail = ''""")


def _create_job(store: Any, job_type: str = "tts.synthesize") -> Any:
    from app.jobs.models import CreateJobRequest, ResourceClass

    return store.create_job(CreateJobRequest(module="voice", type=job_type, resource_class=ResourceClass.GPU_TTS,
                                             input_payload={"text": "hi"}, max_attempts=3))


def _claim(database: Any, store: Any) -> dict[str, Any] | None:
    from app.persistence.unit_of_work import unit_of_work

    with unit_of_work(database) as work:
        record = work.jobs.claim_next(store.context, worker_id="worker:test", resource_classes=["gpu:tts"],
                                      lease_seconds=30)
        work.commit()
    return record


# --- Deferral -----------------------------------------------------------------------------------


def test_a_deferred_job_waits_and_never_spends_its_attempts(workspace) -> None:
    database, store = workspace
    job = _create_job(store)
    for _ in range(5):  # more deferrals than max_attempts
        claimed = _claim(database, store)
        assert claimed is not None and claimed["id"] == job.id
        deferred = store.defer_job(job.id, delay_seconds=1, reason="waiting for fish-s2-pro",
                                   worker_id="worker:test", lease_token=claimed["lease_token"])
        assert deferred is not None and deferred.status.value == "queued"
        assert _claim(database, store) is None  # not before its delay
        with database.transaction() as connection:
            connection.execute("UPDATE omnix_jobs SET available_at = clock_timestamp() WHERE id = %s", (job.id,))
    claimed = _claim(database, store)
    assert claimed is not None and claimed["attempt_count"] == 1


def test_only_the_lease_holder_can_defer(workspace) -> None:
    from app.persistence.execution_repositories import JobClaimConflict

    database, store = workspace
    job = _create_job(store)
    _claim(database, store)
    with pytest.raises(JobClaimConflict):
        store.defer_job(job.id, delay_seconds=1, worker_id="worker:test", lease_token="not-the-lease")


# --- Swap coordination store -------------------------------------------------------------------


def test_live_sessions_block_and_expire(workspace) -> None:
    from app.persistence import tts_swap

    assert not tts_swap.live_session_active()
    session = tts_swap.acquire_live_session("live_call", "call-1", ttl_seconds=30)
    assert tts_swap.live_session_active()
    tts_swap.release_live_session(session)
    assert not tts_swap.live_session_active()
    tts_swap.acquire_live_session("read_aloud", "call-2", ttl_seconds=1)
    database, _store = workspace
    with database.transaction() as connection:
        connection.execute("UPDATE omnix_tts_live_sessions SET expires_at = clock_timestamp() - INTERVAL '1 second'")
    assert not tts_swap.live_session_active()


def test_the_swap_lease_is_exclusive_fenced_and_recoverable(workspace) -> None:
    from app.persistence import tts_swap

    database, _store = workspace
    fence = tts_swap.begin_swap("controller-a", engine="fish-s2-pro", restore_engine="faster-qwen3-tts", lease_seconds=60)
    assert fence is not None
    assert tts_swap.begin_swap("controller-b", engine="x", restore_engine="y", lease_seconds=60) is None
    with pytest.raises(tts_swap.SwapFenceLost):
        tts_swap.update_swap(fence - 1, phase="active")
    assert tts_swap.update_swap(fence, phase="active").phase == "active"
    with database.transaction() as connection:
        connection.execute("UPDATE omnix_tts_swap_state SET lease_expires_at = clock_timestamp() - INTERVAL '1 second'")
    state = tts_swap.swap_state()
    assert state.lease_expired and state.restore_engine == "faster-qwen3-tts"
    newer = tts_swap.begin_swap("controller-b", engine="x", restore_engine="y", lease_seconds=60)
    assert newer == fence + 1
    with pytest.raises(tts_swap.SwapFenceLost):
        tts_swap.update_swap(fence, phase="active")  # the crashed holder's fence is dead
    assert tts_swap.end_swap(newer)
    assert tts_swap.swap_state().idle


def test_swap_requests_queue_serve_and_finish(workspace) -> None:
    from app.persistence import tts_swap

    tts_swap.request_swap("fish-s2-pro", "job:a")
    tts_swap.request_swap("fish-s2-pro", "job:a")  # one pending request per job
    tts_swap.request_swap("faster-qwen3-tts", "job:b")
    assert [request["job_id"] for request in tts_swap.pending_swap_requests()] == ["job:a", "job:b"]
    assert tts_swap.swap_requests_pending()
    assert tts_swap.resolve_swap_requests("fish-s2-pro", "served") == 1
    assert tts_swap.engine_in_use("fish-s2-pro")  # served: the job runs on it
    tts_swap.finish_swap_request("job:a")
    assert not tts_swap.engine_in_use("fish-s2-pro")
    tts_swap.resolve_swap_requests("faster-qwen3-tts", "failed", "needs 30 GB")
    assert tts_swap.swap_request_failure("job:b") == "needs 30 GB"
    assert not tts_swap.swap_requests_pending()


# --- The controller over the real store, with a fake TTS service ------------------------------


class _Service:
    def __init__(self, loaded: str = "faster-qwen3-tts", free_gb: float = 20.0) -> None:
        from app.platform.voice.swap_controller import ServiceHealth

        self.loaded = loaded
        self.fence: int | None = None
        self.free_gb = free_gb
        self.calls: list[tuple[str, str, int]] = []
        self._health = ServiceHealth

    def health(self):
        return self._health(loaded_engine=self.loaded, swap_fence=self.fence, vram_free_bytes=int(self.free_gb * 1024 ** 3))

    def swap(self, engine: str, fence: int, restore: str) -> dict:
        self.calls.append(("swap", engine, fence))
        self.loaded, self.fence = engine, fence
        return {"ok": True}

    def restore(self, engine: str, fence: int) -> dict:
        self.calls.append(("restore", engine, fence))
        self.loaded, self.fence = engine, None
        return {"ok": True}

    def live_request(self, engine: str) -> None:
        """What the TTS service does for live speech during a swap."""
        self.loaded, self.fence = engine, None


def _controller(service: Any, **kwargs: Any):
    from app.platform.voice.swap_controller import SwapController, vram_estimate

    kwargs.setdefault("holder_id", "controller-test")
    return SwapController(service, selected_engine=lambda: "faster-qwen3-tts", vram_needed_gb=vram_estimate, **kwargs)


def test_a_group_swaps_in_runs_and_the_selected_engine_comes_back(workspace) -> None:
    from app.persistence import tts_swap

    service = _Service()
    controller = _controller(service)
    assert controller.tick() == "idle"
    tts_swap.request_swap("fish-s2-pro", "job:1")
    tts_swap.request_swap("fish-s2-pro", "job:2")
    assert controller.tick() == "swapped:fish-s2-pro"
    assert service.loaded == "fish-s2-pro"
    assert controller.tick() == "holding:fish-s2-pro"  # jobs still run on it
    tts_swap.finish_swap_request("job:1")
    tts_swap.finish_swap_request("job:2")
    assert controller.tick() == "restored:faster-qwen3-tts"
    assert service.loaded == "faster-qwen3-tts" and tts_swap.swap_state().idle
    assert [call[0] for call in service.calls] == ["swap", "restore"]


def test_requests_of_jobs_that_ended_never_swap_or_hold_an_engine(workspace) -> None:
    from app.jobs.models import CancelJobRequest, CompleteJobRequest
    from app.persistence import tts_swap

    database, store = workspace
    service = _Service()
    controller = _controller(service)
    cancelled = _create_job(store)  # cancelled while it waited for its engine: its handler never runs again
    tts_swap.request_swap("fish-s2-pro", cancelled.id)
    assert store.request_cancel(cancelled.id, CancelJobRequest(reason="not needed")).status.value == "canceled"
    assert controller.tick() == "idle" and service.calls == []
    assert tts_swap.pending_swap_requests() == []

    served = _create_job(store)  # another module's job finished on the swapped-in engine without closing its request
    tts_swap.request_swap("fish-s2-pro", served.id)
    assert controller.tick() == "swapped:fish-s2-pro"
    claimed = _claim(database, store)
    assert claimed is not None and controller.tick() == "holding:fish-s2-pro"
    store.complete_job(served.id, CompleteJobRequest(output_refs=[], worker_id="worker:test",
                                                     lease_token=claimed["lease_token"]))
    assert controller.tick() == "restored:faster-qwen3-tts"


def test_a_job_running_on_the_loaded_engine_finishes_there_before_a_swap(workspace) -> None:
    from app.apps.audiobook.render_service import _tts_swap_pending
    from app.jobs.models import CompleteJobRequest
    from app.persistence import tts_swap

    database, store = workspace
    service = _Service()
    controller = _controller(service)
    running = _create_job(store)
    claimed = _claim(database, store)
    assert claimed is not None and claimed["id"] == running.id
    tts_swap.request_swap("fish-s2-pro", "job:design")
    assert controller.tick() == "waiting-for-running-jobs" and service.calls == []
    store.complete_job(running.id, CompleteJobRequest(output_refs=[], worker_id="worker:test",
                                                      lease_token=claimed["lease_token"]))
    assert controller.tick() == "swapped:fish-s2-pro"
    # While the swap holds the GPU, audiobook renders wait instead of failing on the swapped engine.
    tts_swap.finish_swap_request("job:design")
    assert not tts_swap.swap_requests_pending() and _tts_swap_pending()


def test_live_speech_blocks_a_swap_from_starting(workspace) -> None:
    from app.persistence import tts_swap

    service = _Service()
    controller = _controller(service)
    session = tts_swap.acquire_live_session("live_call", "call", ttl_seconds=30)
    tts_swap.request_swap("fish-s2-pro", "job:1")
    assert controller.tick() == "waiting-for-live-speech"
    assert service.calls == []
    tts_swap.release_live_session(session)
    assert controller.tick() == "swapped:fish-s2-pro"


def test_live_speech_interrupts_a_swap_and_the_job_asks_again(workspace) -> None:
    from app.persistence import tts_swap

    service = _Service()
    controller = _controller(service)
    tts_swap.request_swap("fish-s2-pro", "job:1")
    controller.tick()
    service.live_request("faster-qwen3-tts")  # a live call arrives
    assert controller.tick() == "interrupted"
    state = tts_swap.swap_state()
    assert state.idle and state.interrupted
    tts_swap.request_swap("fish-s2-pro", "job:1")  # the interrupted job defers and asks again
    assert controller.tick() == "swapped:fish-s2-pro"


def test_the_hold_cap_restores_the_engine_for_other_waiting_jobs(workspace) -> None:
    from app.persistence import tts_swap

    service = _Service()
    clock = {"now": datetime.now(timezone.utc)}
    controller = _controller(service, hold_cap_seconds=60, now=lambda: clock["now"])
    tts_swap.request_swap("fish-s2-pro", "job:long")
    controller.tick()
    tts_swap.request_swap("faster-qwen3-tts", "job:other")
    assert controller.tick() == "holding:fish-s2-pro"
    clock["now"] += timedelta(seconds=120)
    assert controller.tick() == "restored:faster-qwen3-tts"
    assert service.loaded == "faster-qwen3-tts"


def test_a_load_that_does_not_fit_fails_fast_with_what_to_free(workspace) -> None:
    from app.persistence import tts_swap

    service = _Service(free_gb=1.0)  # the LLM holds the rest
    controller = _controller(service)
    tts_swap.request_swap("fish-s2-pro", "job:big")
    assert controller.tick() == "failed:fish-s2-pro"
    assert "unload the local LLM model" in (tts_swap.swap_request_failure("job:big") or "")
    assert service.calls == []


def test_a_crashed_swap_is_restored_when_its_lease_expires(workspace) -> None:
    from app.persistence import tts_swap

    database, _store = workspace
    service = _Service()
    tts_swap.request_swap("fish-s2-pro", "job:1")
    _controller(service).tick()
    assert service.loaded == "fish-s2-pro"
    with database.transaction() as connection:  # the controller's process died
        connection.execute("UPDATE omnix_tts_swap_state SET lease_expires_at = clock_timestamp() - INTERVAL '1 second'")
    survivor = _controller(service, holder_id="controller-survivor")
    assert survivor.tick() == "recovered"
    assert service.loaded == "faster-qwen3-tts" and tts_swap.swap_state().idle


# --- Scripts and takes --------------------------------------------------------------------------


def test_a_saved_script_keeps_line_identity_and_every_take(workspace) -> None:
    from app.platform.voice import scripts_repository as scripts

    saved = scripts.save_script(title="Demo", text="dave: one\nbob: two", engine="fish-s2-pro",
                                casting={"dave": {"voice_id": "voice-cloning:dave", "delivery_instruction": "Warm"}})
    assert [line["speaker"] for line in saved["lines"]] == ["dave", "bob"]
    assert saved["lines"][0]["delivery_instruction"] == "Warm"
    dave, bob = saved["lines"]
    first = scripts.record_take(script_id=saved["id"], line_id=dave["id"], asset_id="audio:t1", job_id="job:1",
                                engine="fish-s2-pro", text="one", duration=1.0)
    second = scripts.record_take(script_id=saved["id"], line_id=dave["id"], asset_id="audio:t2", job_id="job:2",
                                 engine="fish-s2-pro", text="one", duration=1.1)
    loaded = scripts.get_script(saved["id"])
    assert loaded["lines"][0]["selected_take_id"] == second["id"]
    assert {take["asset_id"] for take in loaded["lines"][0]["takes"]} == {"audio:t1", "audio:t2"}
    scripts.select_take(script_id=saved["id"], line_id=dave["id"], take_id=first["id"])
    assert scripts.get_script(saved["id"])["lines"][0]["selected_take_id"] == first["id"]

    # Editing bob's line keeps dave's id and takes; bob's line is new.
    edited = scripts.save_script(title="Demo", text="dave: one\n{pause 600ms}\nbob: two, edited",
                                 script_id=saved["id"], expected_revision=saved["revision"])
    assert edited["revision"] == saved["revision"] + 1
    assert edited["lines"][0]["id"] == dave["id"] and len(edited["lines"][0]["takes"]) == 2
    assert edited["lines"][1]["id"] != bob["id"] and edited["lines"][1]["pause_before_ms"] == 600
    with pytest.raises(scripts.ScriptRevisionConflict):
        scripts.save_script(title="Demo", text="x", script_id=saved["id"], expected_revision=saved["revision"])
    assert scripts.delete_script(saved["id"])
    with pytest.raises(scripts.ScriptNotFound):
        scripts.get_script(saved["id"])


def test_scripts_are_invisible_to_other_workspaces(workspace) -> None:
    """As a runtime-like role (no superuser, no BYPASSRLS), another workspace sees none of the script."""
    import psycopg

    from app.platform.voice import scripts_repository as scripts
    from tests.support.database import admin_database_url

    saved = scripts.save_script(title="Private", text="dave: secret")
    role = "omnix_rls_probe"
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        if not admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            pytest.skip("creating the probe role needs a superuser test database")
        admin.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF; END $$""")
        admin.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        admin.execute(f"GRANT SELECT ON omnix_voice_scripts, omnix_voice_script_lines, omnix_voice_takes TO {role}")
    with psycopg.connect(admin_database_url(), autocommit=True) as probe:
        probe.execute(f"SET ROLE {role}")
        probe.execute("SELECT set_config('omnix.workspace_id', %s, false), set_config('omnix.system', '', false)",
                      (f"workspace:other:{uuid.uuid4().hex}",))
        for table in ("omnix_voice_scripts", "omnix_voice_script_lines"):
            column = "id" if table == "omnix_voice_scripts" else "script_id"
            rows = probe.execute(f"SELECT 1 FROM {table} WHERE {column} = %s", (saved["id"],)).fetchall()
            assert rows == [], table


def test_one_line_renders_again_and_restitch_rebuilds_from_selected_takes(workspace, tmp_path, monkeypatch) -> None:
    import base64

    import numpy as np

    import app.assets as assets_module
    from app.assets.models import AssetType
    from app.jobs.models import JobRecord
    from app.platform.voice import effects
    from app.platform.voice import jobs as voice_jobs
    from app.platform.voice import scripts_repository as scripts

    class _Assets:
        def __init__(self) -> None:
            self.assets: dict[str, Any] = {}

        def get_asset(self, asset_id: str) -> Any:
            return self.assets.get(asset_id)

        def upsert_asset(self, asset: Any) -> Any:
            self.assets[asset.id] = asset
            return asset

    asset_store = _Assets()
    monkeypatch.setattr(assets_module, "default_asset_store", lambda: asset_store)
    monkeypatch.setattr(voice_jobs, "default_asset_store", lambda: asset_store)
    monkeypatch.setattr(voice_jobs, "resources_data_root", lambda: tmp_path)

    rendered: list[str] = []

    class _Engine:
        provider_name = "faster-qwen3-tts"

        def generate_audio(self, text: str, **kwargs: Any) -> dict[str, Any]:
            rendered.append(text)
            tone = 0.3 * np.sin(2 * np.pi * 220 * np.arange(12_000) / 24_000)
            return {"success": True, "audio": base64.b64encode(effects.write_mono(tone, 24_000)).decode("ascii"),
                    "sample_rate": 24_000, "duration": 0.5}

    monkeypatch.setattr("app.providers.service.pinned_tts_provider", lambda name=None: _Engine())

    class _JobStore:
        def __init__(self) -> None:
            self.completed: dict[str, Any] = {}

        def mark_running(self, job_id: str) -> None:
            pass

        def complete_job(self, job_id: str, request: Any) -> None:
            self.completed[job_id] = request

        def fail_job(self, job_id: str, request: Any) -> None:
            pytest.fail(request.message)

    def run(job_type: str, payload: dict[str, Any], job_id: str) -> None:
        store = _JobStore()
        job = JobRecord.model_validate({
            "id": job_id, "module": "voice", "type": job_type, "status": "running", "resource_class": "gpu:tts",
            "input_payload": payload, "created_at": "2026-10-20T00:00:00+00:00", "updated_at": "2026-10-20T00:00:00+00:00",
        })
        voice_jobs.execute_voice_studio_job(store, job)
        assert job_id in store.completed

    script = scripts.save_script(title="Takes", text="dave: one\nbob: two")
    segments = [{"index": line["position"], "speaker": line["speaker"], "text": line["text"], "line_id": line["id"]}
                for line in script["lines"]]
    payload = {"text": script["text"], "script_id": script["id"], "script_segments": segments}
    run("tts.multi_speaker_synthesize", payload, "job:full")
    assert rendered == ["one", "two"]
    lines = scripts.get_script(script["id"])["lines"]
    assert all(len(line["takes"]) == 1 for line in lines)

    # Re-render bob's line only: dave's selected take is reused.
    run("tts.multi_speaker_synthesize", {**payload, "render_line_ids": [lines[1]["id"]]}, "job:bob")
    assert rendered == ["one", "two", "two"]
    lines = scripts.get_script(script["id"])["lines"]
    assert [len(line["takes"]) for line in lines] == [1, 2]

    # Choose bob's first take again and restitch: no synthesis at all.
    first_bob = lines[1]["takes"][-1]["id"]
    scripts.select_take(script_id=script["id"], line_id=lines[1]["id"], take_id=first_bob)
    run("voice.restitch", {"script_id": script["id"]}, "job:restitch")
    assert rendered == ["one", "two", "two"]
    render = asset_store.assets["audio:voice-studio-job-restitch"]
    assert [entry["reused_take_id"] for entry in render.metadata["segment_outputs"]][1] == first_bob
    assert sum(1 for asset in asset_store.assets.values() if asset.type == AssetType.VOICE_TAKE) == 3


def test_a_design_session_stays_loaded_between_previews_unless_another_engine_waits(workspace) -> None:
    from app.persistence import tts_swap
    from app.platform.voice.swap_controller import swap_linger_seconds

    service = _Service()
    controller = _controller(service, linger_seconds=swap_linger_seconds)
    tts_swap.request_swap("qwen3-tts-voicedesign", "job:preview-1")
    assert controller.tick() == "swapped:qwen3-tts-voicedesign"
    tts_swap.finish_swap_request("job:preview-1")
    # The preview finished, but the next one comes within moments: no swap back yet.
    assert controller.tick() == "holding:qwen3-tts-voicedesign"
    tts_swap.request_swap("qwen3-tts-voicedesign", "job:preview-2")
    assert controller.tick() == "holding:qwen3-tts-voicedesign"
    tts_swap.finish_swap_request("job:preview-2")
    assert [call[0] for call in service.calls] == ["swap"]
    # Another engine waiting ends the linger at once.
    tts_swap.request_swap("fish-s2-pro", "job:render")
    assert controller.tick() == "restored:faster-qwen3-tts"
    # Ordinary engines restore as soon as their jobs finish.
    assert swap_linger_seconds("fish-s2-pro") == 0.0


def test_selecting_an_engine_holds_the_swap_lease_so_no_swap_races_it(workspace, monkeypatch) -> None:
    from app.persistence import tts_swap
    from app.platform.voice import tts_engines

    monkeypatch.setattr("app.platform.voice.swap_controller.swaps_enabled", lambda: True)
    monkeypatch.setattr("app.settings.access.load_settings", lambda: {"audio_provider_tts": "fish-s2-pro"})
    monkeypatch.setattr("app.settings.access.save_settings", lambda values: None)
    # Never touch the real Voice Library or STT service from a test.
    monkeypatch.setattr(tts_engines, "prepare_voice_transcripts", lambda: pytest.fail("no transcripts for Qwen"))
    seen: dict[str, Any] = {}

    def switch(provider_id: str) -> None:
        seen["state"] = tts_swap.swap_state()
        # The controller sees the lease taken and leaves it alone.
        seen["tick"] = _controller(_Service()).tick() if tts_swap.request_swap("fish-s2-pro", "job:x") is None else ""

    monkeypatch.setattr("app.providers.service.invalidate_audio_provider_cache", lambda kind=None: None)
    monkeypatch.setattr("app.platform.voice.tts_runtime_actions.warm_tts_runtime",
                        lambda reason: switch("faster-qwen3-tts") or {"status": "ready"})

    class _Thread:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    # Only tts_engines' own view of threading: the shared module drives psycopg's pool threads.
    from types import SimpleNamespace

    monkeypatch.setattr(tts_engines, "threading", SimpleNamespace(Thread=_Thread))
    tts_engines._update(phase="idle")
    tts_engines.select_tts_engine("faster-qwen3-tts")
    assert seen["state"].engine == "faster-qwen3-tts" and not seen["state"].idle
    assert seen["tick"] == "held-elsewhere"
    assert tts_swap.swap_state().idle  # released when the switch finished
    tts_swap.finish_swap_request("job:x")

    # While a voice tool holds the lease, selection is refused.
    fence = tts_swap.begin_swap("controller", engine="qwen3-tts-voicedesign", restore_engine="faster-qwen3-tts",
                                lease_seconds=60)
    with pytest.raises(RuntimeError, match="swapped in"):
        tts_engines.select_tts_engine("faster-qwen3-tts")
    assert tts_engines._SWITCH["phase"] != "unloading"
    tts_swap.end_swap(fence)


def test_a_load_longer_than_the_lease_is_not_taken_over(workspace) -> None:
    """The controller renews its lease while an engine loads, so another process does not "recover" it."""
    import time

    from app.persistence import tts_swap

    seen: list[str] = []

    class _SlowService(_Service):
        def swap(self, engine: str, fence: int, restore: str) -> dict:
            time.sleep(7)  # past the 5 s lease
            seen.append(other.tick())  # another worker process's controller, mid-load
            return super().swap(engine, fence, restore)

    service = _SlowService()
    other = _controller(_Service(), holder_id="other-process", lease_seconds=5)
    controller = _controller(service, lease_seconds=5)
    tts_swap.request_swap("fish-s2-pro", "job:1")
    assert controller.tick() == "swapped:fish-s2-pro"
    assert seen == ["held-elsewhere"] and service.loaded == "fish-s2-pro"


def test_a_restore_that_fails_is_retried_until_the_selected_engine_is_back(workspace) -> None:
    """A selected engine that cannot load yet (host memory short) is restored later, not abandoned."""
    from app.persistence import tts_swap
    from app.platform.voice.swap_controller import SwapServiceError

    class _ShortOnMemory(_Service):
        refusals = 1

        def restore(self, engine: str, fence: int) -> dict:
            if self.refusals:
                self.refusals -= 1
                self.calls.append(("restore-refused", engine, fence))
                raise SwapServiceError("/api/tts/engine/restore answered 503: host memory is short")
            return super().restore(engine, fence)

    service = _ShortOnMemory()
    controller = _controller(service, restore_retry_seconds=0.0)
    tts_swap.request_swap("fish-s2-pro", "job:1")
    assert controller.tick() == "swapped:fish-s2-pro"
    tts_swap.finish_swap_request("job:1")
    assert controller.tick() == "restored:faster-qwen3-tts"   # the attempt was refused
    assert tts_swap.swap_state().phase == "restoring"
    assert controller.tick() == "restored:faster-qwen3-tts"
    assert service.loaded == "faster-qwen3-tts" and tts_swap.swap_state().idle
    assert [call[0] for call in service.calls] == ["swap", "restore-refused", "restore"]


def test_while_a_restore_keeps_failing_waiting_requests_fail_with_the_reason(workspace) -> None:
    from app.persistence import tts_swap
    from app.platform.voice.swap_controller import SwapServiceError

    class _NeverRestores(_Service):
        def restore(self, engine: str, fence: int) -> dict:
            raise SwapServiceError("/api/tts/engine/restore answered 503: host memory is short")

    controller = _controller(_NeverRestores(), restore_retry_seconds=3600.0)
    tts_swap.request_swap("fish-s2-pro", "job:1")
    assert controller.tick() == "swapped:fish-s2-pro"
    tts_swap.finish_swap_request("job:1")
    controller.tick()                                     # the restore is refused
    tts_swap.request_swap("qwen3-tts-voicedesign", "job:2")
    assert controller.tick() == "restore-waiting"
    failure = tts_swap.swap_request_failure("job:2")
    assert failure and "could not be loaded again" in failure
