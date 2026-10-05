"""Adding an app is a recipe: scaffold, register two lines, and every gate passes (ADR-0016, PA-4.2).

The scaffold runs in a throwaway git worktree of the current tree (HEAD plus
the uncommitted changes), so the repository itself is never touched. The new
module is migrated into a fresh PostgreSQL database, its route, job and setting
are exercised through the gateway, a second workspace cannot see or write its
rows, and with the module disabled the gateway still starts and the
architecture gates still pass.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from .conftest import run_checked as _run

MODULE_ID = "recipe-probe"
PACKAGE = "recipe_probe"
PROBE_ROLE = "omnix_rls_probe"

pytestmark = [pytest.mark.postgres, pytest.mark.slow]

_GATEWAY_PROBE = """
import json, sys, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.composition.gateway.main import create_gateway_app
from app.jobs.handlers import JobExecutionContext
from tests.support.in_memory_jobs import InMemoryJobStore

store = InMemoryJobStore(Path(tempfile.mkdtemp()) / "jobs.sqlite")
app = create_gateway_app(job_store_factory=lambda: store)
client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
from app.persistence.database import default_database
from app.persistence.identity_service import ensure_local_identity
from app.persistence.runtime import ensure_postgresql_runtime_ready
from app.runtime.tenant_context import install_process_tenant

# A fresh install becomes the PostgreSQL authority, as the persistence tests set it up.
ensure_postgresql_runtime_ready(default_database(), auto_initialize_fresh_install=True, apply_schema_changes=False)
install_process_tenant(ensure_local_identity(default_database()))
if sys.argv[1] == "disabled":
    print(json.dumps({"items": client.get("/api/recipe-probe/items").status_code,
                      "health": client.get("/health").status_code}))
    raise SystemExit(0)
created = client.post("/api/recipe-probe/items", json={"name": "first"}).json()
settings = client.get("/api/recipe-probe/settings").json()
job = client.post("/api/jobs", json={
    "module": "recipe-probe", "type": "recipe_probe.note", "resource_class": "cpu",
    "input_payload": {"item_id": created["id"], "body": "hello"},
}).json()
app.state.job_handler_registry.execute(JobExecutionContext(job_store=store), store.get_job(job["id"]))
print(json.dumps({"created": created, "settings": settings, "job": str(store.get_job(job["id"]).status.value),
                  "items": client.get("/api/recipe-probe/items").json()}))
"""


def _changed_outside_module(tree: Path) -> set[str]:
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=tree,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    module_paths = (f"src/app/apps/{PACKAGE}/", f"src/tests/{PACKAGE}/", f"web/src/features/{MODULE_ID}/")
    return {line[3:] for line in status if not line[3:].startswith(module_paths)}


def _tenant_isolation(url: str, item_owner: str) -> dict[str, object]:
    """What a runtime-like role sees and may write from another workspace."""
    import psycopg

    other = f"workspace:recipe-other-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PROBE_ROLE}') THEN
                CREATE ROLE {PROBE_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF; END $$""")
        admin.execute(f"GRANT USAGE ON SCHEMA public TO {PROBE_ROLE}")
        admin.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {PROBE_ROLE}")
        admin.execute("INSERT INTO omnix_users (id, display_name) VALUES ('user:recipe', 'recipe') ON CONFLICT DO NOTHING")
        admin.execute("INSERT INTO omnix_workspaces (id, name, created_by) VALUES (%s, %s, 'user:recipe')", (other, other))
        item_id = admin.execute(f"SELECT id FROM omnix_{PACKAGE}_items LIMIT 1").fetchone()[0]
    seen: dict[str, object] = {}
    # Autocommit keeps SET ROLE and the workspace setting in force between statements.
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(f"SET ROLE {PROBE_ROLE}")
        for label, workspace in (("owner", item_owner), ("other", other)):
            connection.execute("SELECT set_config('omnix.workspace_id', %s, false)", (workspace,))
            seen[label] = (
                connection.execute(f"SELECT count(*) FROM omnix_{PACKAGE}_items").fetchone()[0],
                connection.execute(f"SELECT count(*) FROM omnix_{PACKAGE}_notes").fetchone()[0],
                connection.execute(f"UPDATE omnix_{PACKAGE}_items SET name = name").rowcount,
            )
        connection.execute("SELECT set_config('omnix.workspace_id', %s, false)", (other,))
        try:
            connection.execute(f"INSERT INTO omnix_{PACKAGE}_notes (id, item_id, body) VALUES ('x', %s, 'x')", (item_id,))
            seen["other_child_write"] = "allowed"
        except psycopg.errors.InsufficientPrivilege:
            seen["other_child_write"] = "refused"
    return seen


def test_a_scaffolded_app_is_two_registration_lines_and_passes_every_gate(worktree: Path, fresh_database: str) -> None:
    before = _changed_outside_module(worktree)
    env = {**os.environ, "PYTHONPATH": str(worktree / "src"), "OMNIX_ALLOWED_HOSTS": "testserver",
           "OMNIX_DATABASE_URL": fresh_database, "OMNIX_MIGRATION_DATABASE_URL": fresh_database}

    _run([sys.executable, "scripts/new_module.py", MODULE_ID, "--tier", "app", "--web"], worktree, env)
    changed = _changed_outside_module(worktree) - before
    generated = {"web/src/api/generated/openapi.json", "web/src/api/generated/route-owners.json"}
    assert changed - generated == {"src/app/runtime/feature_catalog.py", "web/src/app/modulesManifest.ts"}

    _run([sys.executable, "-m", "app.persistence", "migrate"], worktree, env)
    probe = json.loads(_run([sys.executable, "-c", _GATEWAY_PROBE, "enabled"], worktree, env).stdout.splitlines()[-1])
    assert probe["settings"] == {"greeting": "Hello"}
    assert probe["job"] == "completed"
    assert probe["items"]["items"] == [{"id": probe["created"]["id"], "name": "first", "notes": ["hello"]}]

    import psycopg

    with psycopg.connect(fresh_database) as connection:
        owner = connection.execute(f"SELECT workspace_id FROM omnix_{PACKAGE}_items LIMIT 1").fetchone()[0]
    seen = _tenant_isolation(fresh_database, owner)
    assert seen["owner"] == (1, 1, 1)
    assert seen["other"] == (0, 0, 0)
    assert seen["other_child_write"] == "refused"

    disabled = {**env, "OMNIX_FEATURES_DISABLED": MODULE_ID}
    probe = json.loads(_run([sys.executable, "-c", _GATEWAY_PROBE, "disabled"], worktree, disabled).stdout.splitlines()[-1])
    assert probe == {"items": 404, "health": 200}

    _run(["git", "add", "-A", "--", "src", "scripts", "resources"], worktree)
    conformance = _run([sys.executable, "scripts/module_conformance.py"], worktree, env).stdout
    assert f"{MODULE_ID}: conforms" in conformance
    _run([sys.executable, "scripts/architecture_lint.py", "--check", "--output", str(worktree.parent / "lint.json")], worktree, env)
