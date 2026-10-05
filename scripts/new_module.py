"""Scaffold a new Omnix module (ADR-0016, PA-4.2).

    python scripts/new_module.py <module-id> --tier app|platform [--web] [--no-generate]

Writes the module anatomy (roadmap §1.2) under ``src/app/<package>/``: the
FeatureModule, a contract, a service and repository, an example durable job,
``declarations.py`` (settings section, retention, permissions) and a migration
creating a tenant-isolated table and a child table that follows it, with the
retention policy row. Also writes ``src/tests/<package>/`` and, with
``--web``, the HTTP routes and ``src/apps/web/src/features/<module-id>/``.

Hand-edited outside the module: the catalog line in
``src/app/runtime/feature_catalog.py`` and, with ``--web``, the manifest line in
``src/apps/web/src/app/modulesManifest.ts``. The generators then refresh the
OpenAPI document, its route owners and the web types (skipped with
``--no-generate``, and the web types when the web packages are not installed).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app"
CATALOG = APP / "runtime" / "feature_catalog.py"
WEB = ROOT / "src" / "apps" / "web"
WEB_MANIFESTS = WEB / "src" / "app" / "modulesManifest.ts"
MODULE_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class ScaffoldError(RuntimeError):
    pass


def names(module_id: str) -> dict[str, str]:
    parts = module_id.split("-")
    return {
        "id": module_id,
        "pkg": module_id.replace("-", "_"),
        "title": " ".join(part.capitalize() for part in parts),
        "pascal": "".join(part.capitalize() for part in parts),
        "camel": parts[0] + "".join(part.capitalize() for part in parts[1:]),
    }


def next_migration_version() -> int:
    """One above the highest numeric migration prefix anywhere (PA-2.3 discovery)."""
    sys.path.insert(0, str(ROOT / "src"))
    from app.persistence.migrations import migration_roots

    versions = [int(match[1]) for root in migration_roots() for path in root.glob("*.sql")
                if (match := re.match(r"(\d+)_", path.name))]
    return max(versions, default=0) + 1


def _contracts(n: dict[str, str]) -> str:
    title, pascal = n["title"], n["pascal"]
    return f'''"""What other modules may import from {title} (ADR-0016): its DTOs and ports."""
from __future__ import annotations

from pydantic import BaseModel, Field


class {pascal}Item(BaseModel):
    """One item and its notes."""

    id: str
    name: str
    notes: list[str] = Field(default_factory=list)
'''


def _declarations(n: dict[str, str]) -> str:
    pkg, title, pascal, mid = n["pkg"], n["title"], n["pascal"], n["id"]
    return f'''"""What the kernel reads about {title} without loading it (ADR-0016): kernel imports only."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.persistence.declarations import (
    FeaturePermissions,
    PermissionDeclaration,
    RetentionDeclaration,
    SettingsSection,
)


class {pascal}SettingsProfile(BaseModel):
    """{title}'s section of the settings profile."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    greeting: str = "Hello"


def _delete_expired_notes(connection: Any, retention_days: int, batch_size: int) -> int:
    return int(connection.execute(
        """DELETE FROM omnix_{pkg}_notes WHERE id IN (
               SELECT id FROM omnix_{pkg}_notes
                WHERE created_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 day')
                ORDER BY created_at, id LIMIT %s)""",
        (retention_days, batch_size),
    ).rowcount)


SETTINGS = (SettingsSection("{pkg}", {pascal}SettingsProfile, order=80),)
RETENTION = (RetentionDeclaration("{pkg}_notes", delete=_delete_expired_notes),)
PERMISSIONS = (
    FeaturePermissions(
        "{mid}",
        read=PermissionDeclaration("{pkg}:read", "{title} (read)", member=True),
        write=PermissionDeclaration("{pkg}:write", "{title} (write)", member=True),
    ),
)
'''


def _repository(n: dict[str, str]) -> str:
    pkg, title, pascal = n["pkg"], n["title"], n["pascal"]
    return f'''"""Every SQL statement of {title}, against its own tables only."""
from __future__ import annotations

import uuid
from typing import Any

from app.persistence.tenant import TenantContext


class Postgres{pascal}Repository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def create_item(self, context: TenantContext, *, item_id: str, name: str) -> None:
        self.connection.execute(
            "INSERT INTO omnix_{pkg}_items (id, workspace_id, name) VALUES (%s, %s, %s)",
            (item_id, context.workspace_id, name),
        )

    def items(self, context: TenantContext) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            "SELECT id, name FROM omnix_{pkg}_items WHERE workspace_id = %s ORDER BY created_at, id LIMIT 200",
            (context.workspace_id,),
        ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def notes(self, context: TenantContext) -> dict[str, list[str]]:
        rows = self.connection.execute(
            """SELECT note.item_id, note.body
                 FROM omnix_{pkg}_notes AS note
                 JOIN omnix_{pkg}_items AS item ON item.id = note.item_id
                WHERE item.workspace_id = %s
                ORDER BY note.created_at, note.id
                LIMIT 1000""",
            (context.workspace_id,),
        ).fetchall()
        found: dict[str, list[str]] = {{}}
        for item_id, body in rows:
            found.setdefault(str(item_id), []).append(str(body))
        return found

    def add_note(self, context: TenantContext, *, item_id: str, body: str) -> bool:
        """Add a note to an item of this workspace; ``False`` when there is no such item."""
        cursor = self.connection.execute(
            """INSERT INTO omnix_{pkg}_notes (id, item_id, body)
               SELECT %s, id, %s FROM omnix_{pkg}_items WHERE workspace_id = %s AND id = %s""",
            (f"{pkg}-note:{{uuid.uuid4().hex}}", body, context.workspace_id, item_id),
        )
        return cursor.rowcount == 1
'''


def _service(n: dict[str, str]) -> str:
    pkg, title, pascal = n["pkg"], n["title"], n["pascal"]
    return f'''"""{title} workflows and their transactions; no SQL."""
from __future__ import annotations

import uuid
from typing import Any

from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .contracts import {pascal}Item
from .repository import Postgres{pascal}Repository


def create_item(database: Any, context: TenantContext, name: str) -> {pascal}Item:
    item = {pascal}Item(id=f"{pkg}:{{uuid.uuid4().hex}}", name=name)
    with unit_of_work(database) as work:
        Postgres{pascal}Repository(work.connection).create_item(context, item_id=item.id, name=item.name)
        work.commit()
    return item


def list_items(database: Any, context: TenantContext) -> list[{pascal}Item]:
    with unit_of_work(database) as work:
        repository = Postgres{pascal}Repository(work.connection)
        notes = repository.notes(context)
        items = [{pascal}Item(id=item_id, name=name, notes=notes.get(item_id, [])) for item_id, name in repository.items(context)]
        work.rollback()
    return items


def add_note(database: Any, context: TenantContext, item_id: str, body: str) -> bool:
    with unit_of_work(database) as work:
        added = Postgres{pascal}Repository(work.connection).add_note(context, item_id=item_id, body=body)
        work.commit()
    return added
'''


def _jobs(n: dict[str, str]) -> str:
    pkg, title, pascal, mid = n["pkg"], n["title"], n["pascal"], n["id"]
    return f'''"""{title}'s durable job: add a note to an item."""
from __future__ import annotations

from pydantic import BaseModel

from app.jobs.handlers import JobExecutionContext
from app.jobs.models import CompleteJobRequest, FailJobRequest, JobRecord
from app.persistence.database import default_database
from app.runtime.tenant_context import current_tenant

from .service import add_note

NOTE_JOB_TYPE = "{pkg}.note"


class {pascal}NoteJobInput(BaseModel):
    item_id: str
    body: str


def execute_note_job(context: JobExecutionContext, job: JobRecord) -> JobRecord:
    store = context.job_store
    store.mark_running(job.id)
    request = {pascal}NoteJobInput.model_validate(job.input_payload)
    if not add_note(default_database(), current_tenant(), request.item_id, request.body):
        failed = store.fail_job(job.id, FailJobRequest(
            code="{pkg}_item_missing", message="The item does not exist in this workspace.", retryable=False,
        ))
        return failed or job
    completed = store.complete_job(job.id, CompleteJobRequest(
        output_refs=[{{"type": "{pkg}_note", "module": "{mid}", "item_id": request.item_id}}],
    ))
    return completed or job
'''


def _feature(n: dict[str, str], tier: str, web: bool) -> str:
    title, pascal, mid = n["title"], n["pascal"], n["id"]
    routers = "(_router,)" if web else "()"
    route_import = "from .routes import router\n" if web else ""
    router_factory = ("\n\ndef _router(_context: FeatureContext) -> APIRouter:\n    return router\n" if web else "")
    api_import = "from fastapi import APIRouter\n\n" if web else ""
    context_import = "FeatureContext, FeatureModule" if web else "FeatureModule"
    return f'''"""{title} feature declaration."""
from __future__ import annotations

{api_import}from app.jobs.handlers import JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.features import {context_import}

from .jobs import NOTE_JOB_TYPE, {pascal}NoteJobInput, execute_note_job
{route_import}{router_factory}

FEATURE = FeatureModule(
    id="{mid}",
    title="{title}",
    tier="{tier}",
    routers={routers},
    job_handlers=(
        JobHandlerSpec(
            type=NOTE_JOB_TYPE,
            handler=execute_note_job,
            input_model={pascal}NoteJobInput,
            resource_class=ResourceClass.CPU,
            timeout_seconds=60,
        ),
    ),
)
'''


def _routes(n: dict[str, str]) -> str:
    pkg, title, pascal, mid = n["pkg"], n["title"], n["pascal"], n["id"]
    return f'''"""{title}'s HTTP API."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.persistence.database import default_database
from app.runtime.tenant_context import current_tenant
from app.settings.effective_defaults import load_effective_profile

from . import service
from .contracts import {pascal}Item

router = APIRouter()


class Create{pascal}ItemRequest(BaseModel):
    name: str


class {pascal}ItemList(BaseModel):
    items: list[{pascal}Item]


class {pascal}Settings(BaseModel):
    greeting: str


@router.get("/api/{mid}/items", response_model={pascal}ItemList)
def list_items() -> {pascal}ItemList:
    return {pascal}ItemList(items=service.list_items(default_database(), current_tenant()))


@router.post("/api/{mid}/items", response_model={pascal}Item)
def create_item(request: Create{pascal}ItemRequest) -> {pascal}Item:
    return service.create_item(default_database(), current_tenant(), request.name)


@router.get("/api/{mid}/settings", response_model={pascal}Settings)
def settings() -> {pascal}Settings:
    return {pascal}Settings(greeting=load_effective_profile().{pkg}.greeting)
'''


def _migration(n: dict[str, str]) -> str:
    pkg, title = n["pkg"], n["title"]
    return f'''-- omnix-migration: phase=expand transactional=true
-- {title} (scaffolded, PA-4.2): items owned by a workspace, and their notes.

CREATE TABLE IF NOT EXISTS omnix_{pkg}_items (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES omnix_workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_omnix_{pkg}_items_workspace ON omnix_{pkg}_items (workspace_id, created_at, id);

-- Row-level security, the same policy as 0106_row_level_security.sql.
ALTER TABLE omnix_{pkg}_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_{pkg}_items FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON omnix_{pkg}_items
    USING (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on')
    WITH CHECK (workspace_id = current_setting('omnix.workspace_id', true) OR current_setting('omnix.system', true) = 'on');

-- A child table without workspace_id follows its parent row (PA-4.1 pattern).
CREATE TABLE IF NOT EXISTS omnix_{pkg}_notes (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES omnix_{pkg}_items(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_omnix_{pkg}_notes_item ON omnix_{pkg}_notes (item_id);
CREATE INDEX IF NOT EXISTS idx_omnix_{pkg}_notes_created ON omnix_{pkg}_notes (created_at, id);
ALTER TABLE omnix_{pkg}_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE omnix_{pkg}_notes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON omnix_{pkg}_notes
    USING (EXISTS (SELECT 1 FROM omnix_{pkg}_items AS parent WHERE parent.id = omnix_{pkg}_notes.item_id))
    WITH CHECK (EXISTS (SELECT 1 FROM omnix_{pkg}_items AS parent WHERE parent.id = omnix_{pkg}_notes.item_id));

-- The retention policy for the notes this module declares (declarations.py).
INSERT INTO omnix_retention_policies (record_type, retention_days, terminal_only, enabled, metadata)
VALUES ('{pkg}_notes', 30, FALSE, TRUE, '{{}}'::jsonb)
ON CONFLICT DO NOTHING;
'''


def _module_test(n: dict[str, str], tier: str) -> str:
    pkg, title, mid = n["pkg"], n["title"], n["id"]
    return f'''"""{title} declares its anatomy (scaffolded, PA-4.2)."""
from __future__ import annotations

from app.runtime.feature_catalog import load_feature


def test_the_module_declares_its_tier_and_job() -> None:
    feature = load_feature("{mid}")

    assert feature.tier == "{tier}"
    assert [spec.type for spec in feature.job_handlers] == ["{pkg}.note"]
'''


def backend_files(n: dict[str, str], *, tier: str, web: bool, version: int) -> dict[Path, str]:
    """The module package, its migration and its test directory."""
    pkg, title = n["pkg"], n["title"]
    base = APP / pkg
    tests = ROOT / "src" / "tests" / pkg
    files = {
        base / "__init__.py": f'"""{title} module (scaffolded by scripts/new_module.py, PA-4.2)."""\n',
        base / "contracts.py": _contracts(n),
        base / "declarations.py": _declarations(n),
        base / "repository.py": _repository(n),
        base / "service.py": _service(n),
        base / "jobs.py": _jobs(n),
        base / "feature.py": _feature(n, tier, web),
        base / "migrations" / f"{version:04d}_{pkg}_initial.sql": _migration(n),
        tests / "__init__.py": "",
        tests / f"test_{pkg}_module.py": _module_test(n, tier),
    }
    if web:
        files[base / "routes.py"] = _routes(n)
    return files


def web_files(n: dict[str, str]) -> dict[Path, str]:
    mid, pascal, camel, title = n["id"], n["pascal"], n["camel"], n["title"]
    base = WEB / "src" / "features" / mid
    return {
        base / "module.ts": f'''import {{ defineModule }} from '../../app/moduleManifest';

/** The workspace module this feature provides (scaffolded, PA-4.2). */
export const {camel}Module = defineModule({{
  id: '{mid}',
  label: '{title}',
  summary: '{title} items and notes.',
  route: '/{mid}',
  icon: '◇',
  backendModules: ['{mid}'],
  apiPrefixes: ['/api/{mid}'],
  loadWorkspace: () => import('./{pascal}Workspace').then((module) => module.{pascal}Workspace),
}});
''',
        base / "index.ts": f'''/** The {mid} feature's public API. */
export {{ {camel}Module }} from './module';
''',
        base / "api" / "gateway.ts": f'''import type {{ paths as CorePaths }} from '../../../api/generated/core';
import {{ createGatewayClient }} from '../../../api/http';
import type {{ paths }} from './generated';

/** The {mid} feature's typed gateway client: its own operations and the kernel's (PA-2.4). */
export const api = createApi();

/** The same client over another fetch (tests, calls that skip fetch middleware). */
export function createApi(options: {{ baseUrl?: string; fetchImpl?: typeof fetch }} = {{}}) {{
  return createGatewayClient<CorePaths & paths>(options);
}}
''',
        base / f"{pascal}Workspace.tsx": f'''import {{ Stack, Text, Title }} from '@mantine/core';
import {{ useQuery }} from '@tanstack/react-query';
import {{ unwrap }} from '../../api/http';
import type {{ OmnixModuleDefinition }} from '../../app/modules';
import {{ WorkspacePanel }} from '../../design/primitives';
import {{ api }} from './api/gateway';

export function {pascal}Workspace({{ module }}: {{ module: OmnixModuleDefinition }}) {{
  const items = useQuery({{ queryKey: ['feature', '{mid}', 'items'], queryFn: () => unwrap(api.GET('/api/{mid}/items')) }});
  return (
    <WorkspacePanel label={{module.label}}>
      <Stack gap="xs">
        <Title order={{2}}>{{module.label}}</Title>
        {{(items.data?.items ?? []).map((item) => <Text key={{item.id}}>{{item.name}}</Text>)}}
      </Stack>
    </WorkspacePanel>
  );
}}
''',
    }


def register(n: dict[str, str], *, web: bool) -> list[Path]:
    """The two registration lines, the only hand edits outside the module."""
    text = CATALOG.read_text(encoding="utf-8")
    entry = f'    "{n["id"]}": "app.{n["pkg"]}.feature:FEATURE",\n'
    closing = text.index("})", text.index("FEATURE_CATALOG"))
    CATALOG.write_text(text[:closing] + entry + text[closing:], encoding="utf-8")
    edited = [CATALOG]
    if web:
        manifests = WEB_MANIFESTS.read_text(encoding="utf-8")
        last_import = max(match.end() for match in re.finditer(r"^import [^\n]*\n", manifests, re.M))
        manifests = (manifests[:last_import] + f"import {{ {n['camel']}Module }} from '../features/{n['id']}/module';\n"
                     + manifests[last_import:])
        manifests = manifests.replace("\n] as const;", f"\n  {n['camel']}Module,\n] as const;", 1)
        WEB_MANIFESTS.write_text(manifests, encoding="utf-8")
        edited.append(WEB_MANIFESTS)
    return edited


def generate(*, web: bool) -> list[str]:
    """Refresh the generated contract files; returns what it skipped."""
    skipped = []
    subprocess.run([sys.executable, "scripts/export_gateway_openapi.py", "src/apps/web/src/api/generated/openapi.json"],
                   cwd=ROOT, check=True)
    node_ready = (ROOT / "node_modules" / "openapi-typescript").is_dir()
    if node_ready:
        subprocess.run(["node", "src/apps/web/scripts/generate-api-types.mjs"], cwd=ROOT, check=True)
    else:
        skipped.append("web types (no node_modules; run `npm --prefix src/apps/web run api:types`)")
    return skipped


def scaffold(module_id: str, *, tier: str, web: bool) -> dict[str, list[Path]]:
    if not MODULE_ID.fullmatch(module_id):
        raise ScaffoldError(f"module id {module_id!r} must be lowercase words joined by '-'")
    if tier not in {"app", "platform"}:
        raise ScaffoldError("tier must be app or platform")
    n = names(module_id)
    if f'"{module_id}":' in CATALOG.read_text(encoding="utf-8") or (APP / n["pkg"]).exists():
        raise ScaffoldError(f"module {module_id!r} already exists")
    files = backend_files(n, tier=tier, web=web, version=next_migration_version())
    if web:
        if (WEB / "src" / "features" / module_id).exists():
            raise ScaffoldError(f"web feature {module_id!r} already exists")
        files.update(web_files(n))
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    return {"written": sorted(files), "edited": register(n, web=web)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("module_id")
    parser.add_argument("--tier", required=True, choices=("app", "platform"))
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--no-generate", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = scaffold(args.module_id, tier=args.tier, web=args.web)
    except ScaffoldError as error:
        print(f"new_module: {error}", file=sys.stderr)
        return 2
    skipped = [] if args.no_generate else generate(web=args.web)
    relative = lambda path: path.relative_to(ROOT).as_posix()  # noqa: E731
    print(f"created {len(result['written'])} files for {args.module_id}")
    print("hand-edited outside the module:")
    for path in result["edited"]:
        print(f"  {relative(path)}")
    if not args.no_generate:
        print("generated: src/apps/web/src/api/generated/ and features/*/api/generated.ts")
    for item in skipped:
        print(f"skipped: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
