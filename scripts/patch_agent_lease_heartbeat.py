from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one match in {path}: found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


repository_path = REPO / "src/app/agent_runtime/repository.py"
service_path = REPO / "src/app/agent_runtime/service_core.py"
test_path = REPO / "src/tests/persistence/test_agent_runtime_repository_integration.py"
workflow_path = REPO / ".github/workflows/agent-runtime.yml"

# Lease acquisition changes ownership generation. Heartbeats must only renew the
# already-owned lease and must preserve the lease token.
repository_text = repository_path.read_text(encoding="utf-8")
if "    def renew_lease(" in repository_text:
    raise RuntimeError("renew_lease already exists")
repository_text += '''\n\n    def renew_lease(self, run_id: str, *, worker_id: str, ttl_seconds: int = 30) -> WorkerLease:\n        """Renew an active lease without touching run state or changing ownership identity.\n\n        Heartbeats are liveness bookkeeping, not ownership acquisition. Keeping\n        renewal on ``omnix_agent_worker_leases`` means review/acceptance can hold\n        the authoritative run row without blocking worker liveness. The stable\n        lease token identifies one ownership generation until the lease expires\n        or another worker acquires it.\n        """\n\n        expires = datetime.now(timezone.utc) + timedelta(seconds=max(5, ttl_seconds))\n        row = self.connection.execute(\n            """\n            UPDATE omnix_agent_worker_leases\n               SET lease_expires_at = %s,\n                   heartbeat_at = CURRENT_TIMESTAMP,\n                   revision = revision + 1\n             WHERE workspace_id = %s AND run_id = %s AND worker_id = %s\n               AND lease_expires_at > CURRENT_TIMESTAMP\n            RETURNING worker_id, lease_token, lease_expires_at, heartbeat_at, revision\n            """,\n            (expires, self.context.workspace_id, run_id, worker_id),\n        ).fetchone()\n        if row is None:\n            owner = self.connection.execute(\n                """\n                SELECT worker_id, lease_expires_at\n                  FROM omnix_agent_worker_leases\n                 WHERE workspace_id = %s AND run_id = %s\n                """,\n                (self.context.workspace_id, run_id),\n            ).fetchone()\n            if owner is None:\n                raise AgentLeaseConflict(f"run {run_id} has no active lease to renew")\n            raise AgentLeaseConflict(\n                f"run {run_id} lease cannot be renewed by {worker_id}; "\n                f"owner={owner[0]} expires_at={owner[1]}"\n            )\n        return WorkerLease(\n            run_id=run_id,\n            worker_id=str(row[0]),\n            lease_token=str(row[1]),\n            lease_expires_at=row[2],\n            heartbeat_at=row[3],\n            revision=int(row[4]),\n        )\n'''
repository_path.write_text(repository_text, encoding="utf-8")

replace_once(
    service_path,
    "from .repository import PostgresAgentRunRepository\n",
    "from .repository import AgentLeaseConflict, PostgresAgentRunRepository\n",
)

replace_once(
    service_path,
    '''            try:\n                self.heartbeat(run_id, ttl_seconds=90)\n            except Exception as exc:\n                log_agent_activity(\n                    "service.supervisor.heartbeat_failed",\n                    category="recovery",\n                    level="error",\n                    run_id=run_id,\n                    fields={"worker_id": self.worker_id},\n                    error=exc,\n                    include_traceback=True,\n                )\n                continue\n            try:\n                self._supervise_stalled_run(run_id)\n''',
    '''            try:\n                self.heartbeat(run_id, ttl_seconds=90)\n            except AgentLeaseConflict as exc:\n                # This worker no longer owns the lease. Continuing its local Pi\n                # process would violate execution authority, so stop supervising\n                # this run immediately and let the current owner proceed.\n                log_agent_activity(\n                    "service.supervisor.lease_lost",\n                    category="recovery",\n                    level="warning",\n                    run_id=run_id,\n                    fields={"worker_id": self.worker_id},\n                    error=exc,\n                )\n                self.runtime.close_run(run_id)\n                continue\n            except Exception as exc:\n                # A transient database failure is not proof that ownership was\n                # lost. Keep normal progress supervision active and retry lease\n                # renewal on the next supervisor cycle.\n                log_agent_activity(\n                    "service.supervisor.heartbeat_failed",\n                    category="recovery",\n                    level="error",\n                    run_id=run_id,\n                    fields={"worker_id": self.worker_id},\n                    error=exc,\n                    include_traceback=True,\n                )\n            try:\n                self._supervise_stalled_run(run_id)\n''',
)

replace_once(
    service_path,
    '''        with unit_of_work(self.database) as work:\n            repository = PostgresAgentRunRepository(work.connection, self.context)\n            repository.acquire_lease(run_id, worker_id=self.worker_id, ttl_seconds=ttl_seconds)\n            repository.append_event(\n                AgentEvent(run_id=run_id, event_type="worker.heartbeat", payload={"worker_id": self.worker_id})\n            )\n            work.commit()\n''',
    '''        with unit_of_work(self.database) as work:\n            repository = PostgresAgentRunRepository(work.connection, self.context)\n            lease = repository.renew_lease(\n                run_id,\n                worker_id=self.worker_id,\n                ttl_seconds=ttl_seconds,\n            )\n            work.commit()\n        log_agent_activity(\n            "service.heartbeat.renewed",\n            category="recovery",\n            run_id=run_id,\n            fields={\n                "worker_id": self.worker_id,\n                "lease_revision": lease.revision,\n                "lease_expires_at": lease.lease_expires_at.isoformat(),\n            },\n        )\n''',
)

replace_once(
    test_path,
    "from app.agent_runtime.service import AgentRunService\n",
    "from app.agent_runtime.service import AgentRunService\nfrom app.agent_runtime.service_core import AgentRunService as CoreAgentRunService\n",
)

with test_path.open("a", encoding="utf-8") as handle:
    handle.write(r'''


def test_lease_renewal_preserves_token_and_requires_active_owner() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-renew-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Renew lease",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            acquired = repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            renewed = repository.renew_lease(run_id, worker_id="worker-a", ttl_seconds=120)
            assert renewed.worker_id == "worker-a"
            assert renewed.lease_token == acquired.lease_token
            assert renewed.revision == acquired.revision + 1
            assert renewed.lease_expires_at >= acquired.lease_expires_at
            with pytest.raises(AgentLeaseConflict):
                repository.renew_lease(run_id, worker_id="worker-b", ttl_seconds=120)
            work.commit()

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            work.connection.execute(
                """
                UPDATE omnix_agent_worker_leases
                   SET lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (context.workspace_id, run_id),
            )
            with pytest.raises(AgentLeaseConflict):
                repository.renew_lease(run_id, worker_id="worker-a", ttl_seconds=120)
            takeover = repository.acquire_lease(run_id, worker_id="worker-b", ttl_seconds=120)
            assert takeover.worker_id == "worker-b"
            assert takeover.lease_token != acquired.lease_token
            work.commit()
    finally:
        database.close()


def test_lease_renewal_does_not_wait_for_authoritative_run_row_lock() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-renew-lock-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Renew while acceptance owns run row",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            work.commit()

        # Simulate review/acceptance holding the authoritative run row. The
        # renewal connection uses an aggressive lock timeout so this becomes a
        # regression test for the exact contention seen in production logs.
        with unit_of_work(database) as run_lock_work:
            run_lock_work.connection.execute(
                """
                SELECT revision
                  FROM omnix_agent_runs
                 WHERE workspace_id = %s AND run_id = %s
                 FOR UPDATE
                """,
                (context.workspace_id, run_id),
            ).fetchone()
            with unit_of_work(database) as renew_work:
                renew_work.connection.execute("SET LOCAL lock_timeout = '250ms'")
                repository = PostgresAgentRunRepository(renew_work.connection, context)
                renewed = repository.renew_lease(run_id, worker_id="worker-a", ttl_seconds=90)
                assert renewed.worker_id == "worker-a"
                renew_work.commit()
            run_lock_work.rollback()
    finally:
        database.close()


def test_service_heartbeat_renews_lease_without_appending_ordered_event() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-heartbeat-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Heartbeat without event contention",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            repository.create_run(spec)
            acquired = repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            before_events = repository.list_events(run_id)
            work.commit()

        service = CoreAgentRunService(database, worker_id="worker-a")
        service._supervisor_started = True
        service.heartbeat(run_id, ttl_seconds=120)

        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            after_events = repository.list_events(run_id)
            lease_row = work.connection.execute(
                """
                SELECT lease_token, revision
                  FROM omnix_agent_worker_leases
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (context.workspace_id, run_id),
            ).fetchone()
            assert [event.event_id for event in after_events] == [event.event_id for event in before_events]
            assert all(event.event_type != "worker.heartbeat" for event in after_events)
            assert lease_row is not None
            assert str(lease_row[0]) == acquired.lease_token
            assert int(lease_row[1]) == acquired.revision + 1
            work.rollback()
    finally:
        database.close()


def test_supervisor_stops_local_runtime_when_lease_authority_is_lost(monkeypatch) -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-lease-loss-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Lose ownership",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id="worker-b", ttl_seconds=90)
            repository.update_state(
                run_id,
                expected_revision=created.revision,
                status="running",
                worker_id="worker-a",
            )
            work.commit()

        service = CoreAgentRunService(database, worker_id="worker-a")
        service._supervisor_started = True
        closed: list[str] = []
        stalled: list[str] = []
        monkeypatch.setattr(service.budgets, "enforce_wall_time", lambda _run_id: None)
        monkeypatch.setattr(service.runtime, "close_run", lambda value: closed.append(value))
        monkeypatch.setattr(service.runtime, "active_run_ids", lambda: set())
        monkeypatch.setattr(service, "recover_orphaned_runs", lambda: [])
        monkeypatch.setattr(service, "_supervise_stalled_run", lambda value: stalled.append(value))

        service._supervise_once()

        assert closed == [run_id]
        assert stalled == []
    finally:
        database.close()


def test_transient_heartbeat_failure_does_not_skip_progress_supervision(monkeypatch) -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        run_id = f"agent-heartbeat-transient-{uuid.uuid4().hex}"
        spec = AgentRunSpec(
            run_id=run_id,
            task="Transient heartbeat failure",
            model=ModelRef(provider_id="test", model_id="model"),
        )
        with unit_of_work(database) as work:
            repository = PostgresAgentRunRepository(work.connection, context)
            created = repository.create_run(spec)
            repository.acquire_lease(run_id, worker_id="worker-a", ttl_seconds=90)
            repository.update_state(
                run_id,
                expected_revision=created.revision,
                status="running",
                worker_id="worker-a",
            )
            work.commit()

        service = CoreAgentRunService(database, worker_id="worker-a")
        service._supervisor_started = True
        stalled: list[str] = []
        monkeypatch.setattr(service.budgets, "enforce_wall_time", lambda _run_id: None)
        monkeypatch.setattr(service, "heartbeat", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("transient db failure")))
        monkeypatch.setattr(service, "_supervise_stalled_run", lambda value: stalled.append(value))
        monkeypatch.setattr(service.runtime, "active_run_ids", lambda: set())
        monkeypatch.setattr(service, "recover_orphaned_runs", lambda: [])

        service._supervise_once()

        assert stalled == [run_id]
    finally:
        database.close()
''')

# Restore the normal read-only workflow in the final committed tree. The
# currently-running workflow has already been loaded by GitHub Actions.
workflow_path.write_text('''name: Omnix Agent Runtime gates

on:
  pull_request:
    branches: [main, "agent/generalized-agent-runtime", "agent/coding-quality-phases-20-31"]
    paths:
      - "src/app/agent_runtime/**"
      - "src/tests/agent_runtime/**"
      - "src/tests/e2e/test_default_llm_agent_ui_flow.py"
      - "src/tests/persistence/test_agent_*"
      - "src/tests/persistence/test_workflow_*"
      - "src/tests/persistence/test_task_graph_*"
      - "src/app/gateway/agent_runtime_routes.py"
      - "src/app/gateway/__init__.py"
      - "src/app/assist_core/hermes_catalog.py"
      - "src/app/assist_core/hermes_client.py"
      - "src/app/assistant_tools/registry.py"
      - "src/app/assistant_tools/hermes_bridge.py"
      - "src/app/assistant_tools/home_adapter.py"
      - "src/app/assistant_tools/trading_adapter.py"
      - "src/app/assistant_tools/config_store.py"
      - "src/app/assistant_tools/repo_adapter.py"
      - "src/app/persistence/migrations/*agent*.sql"
      - "src/app/persistence/migrations/*workflow*.sql"
      - "src/app/persistence/migrations/*task_graph*.sql"
      - "src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx"
      - "src/apps/web/src/features/chatbot/ChatIdentityModeControl.*"
      - "src/apps/web/src/features/chatbot/sessionTools.ts"
      - "src/apps/web/src/features/chatbot/OmnixRunCard.*"
      - "src/apps/web/src/features/chatbot/HtmlArtifactPreview.*"
      - "src/apps/web/src/features/assistant-workspace/assistant-context-controller.ts"
      - "src/apps/web/src/features/assistant-workspace/assistant-context-controller.css"
      - "src/apps/web/src/features/assistant-workspace/assistant-context-controller.test.ts"
      - "src/app/assistant_context/models.py"
      - "src/app/assistant_context/routes.py"
      - "src/app/chat/models.py"
      - "src/app/chat/store.py"
      - "src/app/chat/prompt_store.py"
      - "src/app/chat/prompt_assembly.py"
      - "src/app/chat/prompt_rendering.py"
      - "src/app/chat/routing_context.py"
      - "src/app/chat/history_search.py"
      - "src/app/chat/compaction.py"
      - "src/app/chat/memory_prompt.py"
      - "src/app/chat/live_agent_store.py"
      - "src/app/chat/sqlite_store.py"
      - "src/tests/unit/chat/test_routing_context.py"
      - "src/tests/unit/chat/test_memory_injection.py"
      - "src/tests/unit/assistant_context/test_local_workspace_context.py"
      - "src/apps/web/src/api/client.ts"
      - "src/apps/web/src/api/generated/**"
      - "src/apps/web/package.json"
      - "package-lock.json"
      - ".github/workflows/agent-runtime.yml"
  workflow_dispatch:

concurrency:
  group: omnix-agent-runtime-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  agent-runtime:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    services:
      postgres:
        image: postgres:17-alpine
        env:
          POSTGRES_DB: omnix_test
          POSTGRES_USER: omnix
          POSTGRES_PASSWORD: omnix
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U omnix -d omnix_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 20
    env:
      PYTHONPATH: src
      OMNIX_TEST_DATABASE_URL: postgresql://omnix:omnix@127.0.0.1:5432/omnix_test
      OMNIX_DATABASE_URL: postgresql://omnix:omnix@127.0.0.1:5432/omnix_test
    steps:
      - name: Check out immutable workflow head
        uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
      - name: Verify exact checked-out head
        shell: bash
        run: |
          expected="${{ github.event.pull_request.head.sha || github.sha }}"
          actual="$(git rev-parse HEAD)"
          echo "Expected head: ${expected}"
          echo "Checked out:   ${actual}"
          test "${actual}" = "${expected}"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
      - name: Install Agent Runtime test dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install pytest fastapi httpx pydantic requests python-multipart pillow playwright \\
            "psycopg[binary]>=3.2.1,<4" "psycopg-pool>=3.2.1,<4"
          npm install
      - name: Compile Agent Runtime and Chat context modules
        run: |
          python -m compileall -q src/app/agent_runtime
          python -m compileall -q src/app/chat
      - name: Run Agent Runtime unit and authority tests
        run: |
          python -m pytest src/tests/agent_runtime -q --tb=short
          python -m pytest src/tests/unit/assistant_context/test_local_workspace_context.py -q --tb=short
          python -m pytest \\
            src/tests/unit/chat/test_routing_context.py \\
            src/tests/unit/chat/test_memory_injection.py \\
            -q --tb=short
      - name: Run Agent Runtime PostgreSQL contracts
        run: |
          python -m pytest \\
            src/tests/persistence/test_agent_budget_integration.py \\
            src/tests/persistence/test_agent_runtime_repository_integration.py \\
            src/tests/persistence/test_agent_evidence_integration.py \\
            src/tests/persistence/test_agent_evidence_budget_integration.py \\
            src/tests/persistence/test_agent_coding_quality_integration.py \\
            src/tests/persistence/test_workflow_runtime_integration.py \\
            src/tests/persistence/test_task_graph_repository_integration.py \\
            -q --tb=short
      - name: Run Agent evidence classification and steering contracts
        run: |
          python -m pytest \\
            src/tests/agent_runtime/test_evidence_policy.py \\
            src/tests/agent_runtime/test_classification_matrix.py \\
            -q --tb=short
      - name: Verify default-LLM UI fixture contract
        run: python -m pytest src/tests/e2e/test_default_llm_agent_ui_flow.py -q --tb=short -k fixture_contract
      - name: Run Agent Runtime UI tests
        run: npm --workspace @omnix/web run test -- src/features/chatbot/OmnixRunCard.test.tsx src/features/chatbot/HtmlArtifactPreview.test.tsx src/features/assistant-workspace/assistant-context-controller.test.ts
      - name: Typecheck web integration
        run: npm --workspace @omnix/web run typecheck
      - name: Verify generated gateway API contract
        run: npm --workspace @omnix/web run api:check
''', encoding="utf-8")

# Remove the one-shot helper from the final tree.
Path(__file__).unlink()
