"""Retiring an app is a recipe: drain, cancel, check, remove two lines, tombstone (ADR-0016, PA-4.3).

In a throwaway worktree, a scaffolded module with a tool and an outbox
consumer is migrated into a fresh database and left with a queued job, a
running job, an undelivered event, a pending approval and a stored setting.
``scripts/retire_module.py`` then retires it while a worker finishes the running
job, which submits a follow-up. Afterwards every item is final, the runner
reports no drift, the gateway starts (even with a configuration that still
names the module), the gates pass and the stored setting is intact.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.waiting import wait_until

from .conftest import run_checked as _run

MODULE_ID = "retire-probe"
PACKAGE = "retire_probe"

pytestmark = [pytest.mark.postgres, pytest.mark.slow]

# Gives the scaffolded module a tool and an outbox consumer, and makes its job submit a follow-up.
_EXTENSION = '''

import dataclasses  # noqa: E402

from app.capabilities.registry import TOOL_DECLARATIONS, capability  # noqa: E402
from app.events.outbox_relay import OutboxConsumer  # noqa: E402
from app.jobs.models import CreateJobRequest  # noqa: E402
from app.runtime.ports import ContributionSpec  # noqa: E402


class _ProbeTool:
    tool_id = "retire-probe"
    display_name = "Retire probe"
    description = "Reads retire-probe items."
    account_label = None

    def capabilities(self):
        return (capability("retire_probe.read", "Read items", "Reads retire-probe items.", zone="broker", effect="read"),)

    def default_enabled(self) -> bool:
        return False

    def run(self, request):
        raise NotImplementedError


def _note_then_follow_up(context, job):
    if job.input_payload.get("body") == "chain":
        context.job_store.create_job(CreateJobRequest(
            module="retire-probe", type=NOTE_JOB_TYPE, resource_class="cpu",
            input_payload={"item_id": job.input_payload["item_id"], "body": "follow-up"},
        ))
    return execute_note_job(context, job)


FEATURE = dataclasses.replace(
    FEATURE,
    contributions=(ContributionSpec(TOOL_DECLARATIONS, lambda _context: _ProbeTool()),),
    outbox_consumers=(OutboxConsumer("retire-probe.items", frozenset({"retire_probe_item"}), lambda _c, _e: {}, "item.*"),),
    job_handlers=(dataclasses.replace(FEATURE.job_handlers[0], handler=_note_then_follow_up),),
)
'''

_BOOT = """
import json, sys, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.gateway.main import create_gateway_app
from app.jobs.models import ClaimJobRequest, CreateJobRequest
from app.persistence.database import default_database
from app.persistence.identity_service import ensure_local_identity
from app.persistence.job_store import PostgresJobStoreAdapter
from app.persistence.runtime import ensure_postgresql_runtime_ready
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import install_process_tenant
from app.settings.access import install_database_settings_service
from tests.support.in_memory_jobs import InMemoryJobStore

database = default_database()
ensure_postgresql_runtime_ready(database, auto_initialize_fresh_install=True, apply_schema_changes=False)
context = ensure_local_identity(database)
install_process_tenant(context)
install_database_settings_service(database)
app =create_gateway_app(job_store_factory=lambda: InMemoryJobStore(Path(tempfile.mkdtemp()) / "jobs.sqlite"))
client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
store = PostgresJobStoreAdapter(database)
registry = getattr(app.state, "job_handler_registry", None)
if registry is not None:
    store.configure_handler_registry(registry)
note = lambda item_id, body: CreateJobRequest(module="retire-probe", type="retire_probe.note", resource_class="cpu",
                                              input_payload={"item_id": item_id, "body": body})
"""

# Before retirement: one running (leased) job, one queued job, an undelivered event, a pending approval, a setting.
_SEED = _BOOT + """
item = client.post("/api/retire-probe/items", json={"name": "first"}).json()
saved = client.post("/api/settings/profile", json={"settings_profile_patch": {"retire_probe": {"greeting": "Kept"}}})
assert saved.status_code == 200, saved.text
running = store.create_job(note(item["id"], "chain")).id
claim = store.claim_next(ClaimJobRequest(worker_id="recipe-worker", resource_classes=["cpu"], lease_seconds=600))
assert claim.ok and claim.job.id == running, claim
queued = store.create_job(note(item["id"], "queued")).id
with unit_of_work(database) as work:
    work.outbox.append(context, aggregate_type="retire_probe_item", aggregate_id=item["id"], event_type="item.created",
                       payload={"id": item["id"]}, event_key="retire-probe-undelivered")
    work.connection.execute(
        '''INSERT INTO omnix_capability_approvals (id, workspace_id, subject_type, subject_id, capability_id,
               proposal_digest, proposal_payload, approval_required, requested_by, expires_at)
           VALUES ('retire-probe-approval', %s, 'tool_proposal', 'retire-probe-approval', 'retire_probe.read',
                   %s, '{}'::jsonb, TRUE, %s, CURRENT_TIMESTAMP + INTERVAL '1 hour')''',
        (context.workspace_id, "0" * 64, context.user_id),
    )
    work.commit()
print(json.dumps({"item": item["id"], "running": running, "queued": queued}))
"""

# While the database says draining, in a process whose configuration still enables the module.
_DURING_DRAIN = _BOOT + """
from app.jobs.handlers import JobExecutionContext
from app.persistence.module_states import ModuleNotAcceptingWork
from app.worker_runtime.durable_feature_worker import _LeaseBoundJobStore

ids = json.loads(sys.argv[1])
result = {"write": client.post("/api/retire-probe/items", json={"name": "late"}).status_code,
          "read": client.get("/api/retire-probe/items").status_code}
try:
    store.create_job(note(ids["item"], "outside"))
    result["outside"] = "accepted"
except ModuleNotAcceptingWork:
    result["outside"] = "refused"
job = store.get_job(ids["running"])
finished = registry.execute(JobExecutionContext(job_store=_LeaseBoundJobStore(store, job)), job)
result["running"] = finished.status.value
print(json.dumps(result))
"""

_AFTER = _BOOT + """
from app.settings.effective_defaults import load_effective_profile

print(json.dumps({"items": client.get("/api/retire-probe/items").status_code, "health": client.get("/health").status_code,
                  "settings": load_effective_profile().model_dump(by_alias=True).get("retire_probe")}))
"""


def _python(tree: Path, env: dict[str, str], source: str, *args: str) -> dict:
    return json.loads(_run([sys.executable, "-c", source, *args], tree, env).stdout.splitlines()[-1])


def _rows(url: str, sql: str, params: tuple = ()) -> list[tuple]:
    import psycopg

    with psycopg.connect(url) as connection:
        return connection.execute(sql, params).fetchall()


def _wait_for_state(url: str, state: str, process: subprocess.Popen) -> None:
    seen = wait_until(
        lambda: _rows(url, "SELECT state FROM omnix_module_states WHERE module_id = %s", (MODULE_ID,)),
        lambda rows: rows == [(state,)] or process.poll() is not None, timeout=60, interval=0.2,
    )
    assert seen == [(state,)], f"{MODULE_ID} never became {state}: {process.poll()}"


def _status(tree: Path) -> set[str]:
    lines = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=tree,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    return {line[3:] for line in lines}


def test_a_retired_app_leaves_only_final_work_a_tombstone_and_two_edited_lines(worktree: Path, fresh_database: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(worktree / "src"), "OMNIX_ALLOWED_HOSTS": "testserver",
           "OMNIX_DATABASE_URL": fresh_database, "OMNIX_MIGRATION_DATABASE_URL": fresh_database}
    _run([sys.executable, "scripts/new_module.py", MODULE_ID, "--tier", "app", "--web"], worktree, env)
    feature = worktree / "src" / "app" / PACKAGE / "feature.py"
    feature.write_text(feature.read_text(encoding="utf-8") + _EXTENSION, encoding="utf-8", newline="\n")
    _run(["git", "add", "-A"], worktree)
    _run(["git", "-c", "user.name=recipe", "-c", "user.email=recipe@example.invalid", "commit", "-q", "--no-verify",
          "-m", "scaffold"], worktree)
    _run([sys.executable, "-m", "app.persistence", "migrate"], worktree, env)
    ids = _python(worktree, env, _SEED)

    retiring = subprocess.Popen(
        [sys.executable, "scripts/retire_module.py", MODULE_ID, "--drain-timeout", "45", "--cancel-grace", "1",
         "--poll", "0.3"],
        cwd=worktree, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
    )
    try:
        _wait_for_state(fresh_database, "draining", retiring)
        during = _python(worktree, env, _DURING_DRAIN, json.dumps(ids))
        output, errors = retiring.communicate(timeout=180)
    finally:
        retiring.kill()
    assert retiring.returncode == 0, f"{output}\n{errors}"

    # During the drain: writes refused, reads served, outside jobs refused, the running job finished.
    assert during == {"write": 503, "read": 200, "outside": "refused", "running": "completed"}
    jobs = dict(_rows(fresh_database, "SELECT input_payload->>'body', status || ':' || COALESCE(error->>'code', '') FROM omnix_jobs"))
    assert jobs == {"chain": "completed:", "queued": "canceled:module_retired", "follow-up": "canceled:module_retired"}
    parent = _rows(fresh_database, "SELECT metadata->>'parent_job_id' FROM omnix_jobs WHERE input_payload->>'body' = 'follow-up'")
    assert parent == [(ids["running"],)]
    assert _rows(fresh_database, "SELECT status FROM omnix_outbox_consumer_inbox") == [("dead_letter",)]
    assert _rows(fresh_database, "SELECT reason FROM omnix_outbox_dead_letters") == [("module_retired",)]
    assert _rows(fresh_database, "SELECT decision, reason FROM omnix_capability_approvals") == [("expired", "module_retired")]
    assert _rows(fresh_database, "SELECT state FROM omnix_module_states") == [("retired",)]

    # Only the two registration lines change outside the module, plus the tombstone and generated contracts.
    changed = _status(worktree)
    module_paths = (f"src/app/{PACKAGE}/", f"src/tests/{PACKAGE}/", f"src/apps/web/src/features/{MODULE_ID}/",
                    f"src/app/persistence/retired/{PACKAGE}/")
    generated = {"src/apps/web/src/api/generated/openapi.json", "src/apps/web/src/api/generated/route-owners.json"}
    assert {path for path in changed if not path.startswith(module_paths)} - generated == {
        "src/app/runtime/feature_catalog.py", "src/apps/web/src/app/modulesManifest.ts",
    }
    tombstone = worktree / "src" / "app" / "persistence" / "retired" / PACKAGE
    assert sorted(path.name for path in (tombstone / "migrations").iterdir())[0].endswith(f"_{PACKAGE}_initial.sql")
    assert 'JOB_TYPES: tuple[str, ...] = ("retire_probe.note",)' in (tombstone / "tombstone.py").read_text(encoding="utf-8")
    assert not (worktree / "src" / "app" / PACKAGE).exists()

    # The runner knows every applied migration, the gateway starts, and the stored setting survives.
    _run([sys.executable, "-m", "app.persistence", "migrate"], worktree, env)
    after = _python(worktree, env, _AFTER)
    assert after == {"items": 404, "health": 200, "settings": {"greeting": "Kept"}}
    still_named = _python(worktree, {**env, "OMNIX_FEATURES_DISABLED": MODULE_ID}, _AFTER)
    assert still_named["health"] == 200

    _run(["git", "add", "-A", "--", "src", "scripts", "resources"], worktree)
    owners = _run([sys.executable, "-c", (
        "import sys, json; sys.path.insert(0, 'scripts'); import module_conformance; "
        "print(json.dumps({t: o for t, o in module_conformance._analysis().table_owner_map().items() if 'retire_probe' in t}))"
    )], worktree, env).stdout.splitlines()[-1]
    assert set(json.loads(owners).values()) == {f"retired:{MODULE_ID}"}
    conformance = _run([sys.executable, "scripts/module_conformance.py"], worktree, env).stdout
    assert MODULE_ID not in conformance
    _run([sys.executable, "scripts/architecture_lint.py", "--check", "--output", str(worktree.parent / "lint.json")], worktree, env)
