from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


# P1: evidence identity must come only from provider-originated fields.
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''def _web_source_items(output: dict[str, object]) -> list[dict[str, object]]:
    """Return only provider-returned source records that can carry evidence.

    Request echoes, diagnostics, query text and other envelope metadata are
    intentionally excluded so the search request cannot prove its own subject.
    """

    items = output.get("items")
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, dict)]
''',
    '''def _web_source_items(output: dict[str, object]) -> list[dict[str, object]]:
    """Project web results down to provider-originated evidence fields only.

    Search adapters may synthesize display titles from the request query when a
    provider omits a title. Titles and metadata are therefore presentation data,
    not evidence identity. Only returned URL/content/snippet fields can prove
    subject coverage.
    """

    items = output.get("items")
    if not isinstance(items, list):
        return []
    rows: list[dict[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        projected = {
            key: value
            for key in ("url", "content", "snippet")
            if isinstance((value := item.get(key)), str) and value.strip()
        }
        if projected:
            rows.append(projected)
    return rows
''',
)

# P1: github.com is a hosting venue, not package-owner identity.
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''def _web_domain_trust(source_class: str, domain: str) -> str:
    value = domain.casefold().removeprefix("www.")
    if source_class == "company_filing":
        return "primary" if value == "sec.gov" or value.endswith(".sec.gov") else "reputable"
    if source_class == "software_release":
        return "primary" if value in {"github.com", "postgresql.org"} else "reputable"
    return "reputable"


def _actual_web_trust(output: dict[str, object], source_class: str) -> str:
    items = output.get("items")
    domains: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                domain = urlparse(str(item["url"])).netloc.casefold().removeprefix("www.")
                if domain:
                    domains.append(domain)
    if not domains:
        return "general"
    # A multi-result receipt receives only the trust shared by every result.
    levels = [_web_domain_trust(source_class, domain) for domain in domains]
    return min(levels, key=lambda value: TRUST_RANK.get(value, 0))
''',
    '''_SOFTWARE_RELEASE_PRIMARY_DOMAINS = frozenset({
    "react.dev",
    "vuejs.org",
    "nodejs.org",
    "deno.com",
    "deno.land",
    "bun.sh",
    "postgresql.org",
    "python.org",
    "go.dev",
    "rust-lang.org",
    "kubernetes.io",
    "docker.com",
})
_SOFTWARE_RELEASE_PRIMARY_GITHUB_REPOSITORIES = frozenset({
    "facebook/react",
    "vuejs/core",
    "nodejs/node",
    "denoland/deno",
    "oven-sh/bun",
    "postgres/postgres",
    "python/cpython",
    "golang/go",
    "rust-lang/rust",
    "kubernetes/kubernetes",
    "docker/cli",
})


def _web_item_trust(source_class: str, item: dict[str, object]) -> str:
    parsed = urlparse(str(item.get("url") or ""))
    domain = (parsed.hostname or "").casefold().removeprefix("www.")
    if not domain:
        return "general"
    if source_class == "company_filing":
        return (
            "primary"
            if domain == "sec.gov" or domain.endswith(".sec.gov")
            else "reputable"
        )
    if source_class == "software_release":
        if domain in _SOFTWARE_RELEASE_PRIMARY_DOMAINS:
            return "primary"
        if domain == "github.com":
            segments = [part.casefold() for part in parsed.path.split("/") if part]
            repository = "/".join(segments[:2]) if len(segments) >= 2 else ""
            if repository in _SOFTWARE_RELEASE_PRIMARY_GITHUB_REPOSITORIES:
                return "primary"
        return "reputable"
    return "reputable"


def _actual_web_trust(output: dict[str, object], source_class: str) -> str:
    items = _web_source_items(output)
    if not items:
        return "general"
    levels = [_web_item_trust(source_class, item) for item in items]
    # A multi-result receipt receives only the trust shared by every result.
    return min(levels, key=lambda value: TRUST_RANK.get(value, 0))
''',
)

# P2: direct capability nodes are a fixed-input, explicitly-issued broker primitive.
replace_once(
    "src/app/agent_runtime/task_graph.py",
    'from pydantic import BaseModel, ConfigDict, Field, model_validator\n\n',
    'from pydantic import BaseModel, ConfigDict, Field, model_validator\n\nfrom .capabilities import default_capability_registry\n',
)
replace_once(
    "src/app/agent_runtime/task_graph.py",
    '''        if self.kind == "capability" and not self.capability_id:
            raise ValueError("capability node requires capability_id")
''',
    '''        if self.kind == "capability":
            if not self.capability_id:
                raise ValueError("capability node requires capability_id")
            registry = default_capability_registry()
            capability = registry.get(self.capability_id)
            if capability is None:
                raise ValueError("capability node references unknown capability")
            if capability.execution_zone != "broker":
                raise ValueError("capability node supports broker capabilities only")
            if self.required_local_capabilities:
                raise ValueError("capability node cannot carry local authority")
            issued_external: set[str] = set()
            for value in self.required_external_capabilities:
                canonical = registry.canonical_id(value)
                if canonical is None:
                    raise ValueError("capability node carries unknown external authority")
                issued_external.add(canonical)
            if issued_external != {capability.id}:
                raise ValueError(
                    "capability node must explicitly issue exactly its capability_id"
                )
            if self.workspace is not None:
                raise ValueError("capability node cannot receive workspace authority")
            if self.evidence_policy.requirement != "none":
                raise ValueError(
                    "capability node cannot claim evidence satisfaction directly"
                )
            for scope in self.resource_scopes:
                if registry.canonical_id(scope.capability) != capability.id:
                    raise ValueError(
                        "capability node resource scope must match capability_id"
                    )
''',
)
replace_once(
    "src/app/agent_runtime/task_graph.py",
    '''        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("task graph edge references unknown node")
            if edge.source == edge.target:
                raise ValueError("task graph self-edge is not allowed")
''',
    '''        known = set(node_ids)
        node_by_id = {node.id: node for node in self.nodes}
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError("task graph edge references unknown node")
            if edge.source == edge.target:
                raise ValueError("task graph self-edge is not allowed")
            if edge.kind == "data" and node_by_id[edge.target].kind == "capability":
                raise ValueError(
                    "capability nodes cannot consume predecessor data; "
                    "bind fixed action input in input_template"
                )
''',
)

# P2: dependency-only reads can be prerequisites of read consumers too.
replace_once(
    "src/app/agent_runtime/task_graph.py",
    '''    # Dependency-only profiles are appended after explicit operation segments.
    # If they feed a mutating segment, add an explicit data edge as in the
    # canonical one-node-per-profile compiler.
''',
    '''    # Dependency-only profiles have no explicit operation position. Treat
    # them conservatively as prerequisites of every explicit operation segment;
    # read consumers can depend on another read just as mutations can.
''',
)
replace_once(
    "src/app/agent_runtime/task_graph.py",
    '''        for target_node in operation_segment_nodes:
            if not set(target_node.semantic_action_intents).intersection(
                _MUTATING_ACTIONS
            ):
                continue
            if source_node.id == target_node.id:
''',
    '''        for target_node in operation_segment_nodes:
            if source_node.id == target_node.id:
''',
)
replace_once(
    "src/app/agent_runtime/task_graph.py",
    '''    # A dependency-only profile has no explicit operation position. When the
    # result feeds a stateful/mutating operation, make that dependency explicit
    # instead of allowing the mutation to race the read.
''',
    '''    # A dependency-only profile has no explicit operation position. Preserve
    # it conservatively as a prerequisite of every explicit operation profile;
    # this covers read -> read producer/consumer flows without inventing
    # mutation as a proxy for semantic dependency.
''',
)
replace_once(
    "src/app/agent_runtime/task_graph.py",
    '''            if not set(target_node.semantic_action_intents).intersection(
                _MUTATING_ACTIONS
            ):
                continue
            if any(
''',
    '''            if any(
''',
)

# Defense in depth: fixed capability template input wins over runtime input maps.
replace_once(
    "src/app/agent_runtime/task_graph_runtime.py",
    '                input={**node.input_template, **inputs},\n',
    '                input={**inputs, **node.input_template},\n',
)

# P1: authority revocation is transactional with graph invalidation.
replace_once(
    "src/app/agent_runtime/task_graph_repository.py",
    'from app.persistence.tenant import TenantContext\n\nfrom .task_graph import (\n',
    'from app.persistence.tenant import TenantContext\n\nfrom .contracts import AgentEvent\nfrom .repository import PostgresAgentRunRepository\nfrom .task_graph import (\n',
)
replace_once(
    "src/app/agent_runtime/task_graph_repository.py",
    '''        self.outbox = PostgresOutboxRepository(connection)

    def create_run(
''',
    '''        self.outbox = PostgresOutboxRepository(connection)

    def _revoke_agent_runs(
        self,
        child_run_ids: list[str] | tuple[str, ...] | set[str],
        *,
        reason: str,
    ) -> list[str]:
        ids = sorted({
            str(value).strip()
            for value in child_run_ids
            if str(value).strip()
        })
        if not ids:
            return []
        rows = self.connection.execute(
            """
            UPDATE omnix_agent_runs
               SET status = 'cancel_requested',
                   desired_state = 'cancelled',
                   last_error = %s,
                   revision = revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s
               AND run_id = ANY(%s)
               AND status NOT IN ('completed','failed','cancelled')
               AND desired_state <> 'cancelled'
            RETURNING run_id
            """,
            (
                reason[:2000],
                self.context.workspace_id,
                ids,
            ),
        ).fetchall()
        revoked = [str(row[0]) for row in rows]
        if revoked:
            agent_repository = PostgresAgentRunRepository(
                self.connection,
                self.context,
            )
            for child_run_id in revoked:
                current = agent_repository.get_run(child_run_id)
                agent_repository.append_event(
                    AgentEvent(
                        run_id=child_run_id,
                        event_type="run.status",
                        payload={
                            "status": (
                                current.status
                                if current is not None
                                else "cancel_requested"
                            ),
                            "desired_state": "cancelled",
                            "reason": reason,
                            "source": "task_graph_authority_revocation",
                        },
                    )
                )
        return revoked

    def create_run(
''',
)
replace_once(
    "src/app/agent_runtime/task_graph_repository.py",
    '''        stored = TaskNodeRunState(
            node_id=str(row[0]),
            status=str(row[1]),
            attempts=int(row[2]),
            child_run_id=str(row[3]) if row[3] else None,
            output=dict(row[4] or {}),
            last_error=str(row[5]) if row[5] else None,
            fingerprint=str(row[6]),
            started_at=row[7],
            completed_at=row[8],
        )
        self.append_event(
            TaskGraphEvent(
                run_id=run_id,
                event_type=f"task_graph.node.{status}",
''',
    '''        stored = TaskNodeRunState(
            node_id=str(row[0]),
            status=str(row[1]),
            attempts=int(row[2]),
            child_run_id=str(row[3]) if row[3] else None,
            output=dict(row[4] or {}),
            last_error=str(row[5]) if row[5] else None,
            fingerprint=str(row[6]),
            started_at=row[7],
            completed_at=row[8],
        )
        revoked_child_runs: list[str] = []
        if status == "cancelled" and stored.child_run_id:
            revoked_child_runs = self._revoke_agent_runs(
                [stored.child_run_id],
                reason=f"task_graph_node_cancelled:{run_id}:{node_id}",
            )
        self.append_event(
            TaskGraphEvent(
                run_id=run_id,
                event_type=f"task_graph.node.{status}",
''',
)
replace_once(
    "src/app/agent_runtime/task_graph_repository.py",
    '''                    "error": stored.last_error,
                    "graph_revision": expected_graph_revision,
                },
            )
        )
        return stored
''',
    '''                    "error": stored.last_error,
                    "graph_revision": expected_graph_revision,
                    "revoked_child_runs": revoked_child_runs,
                },
            )
        )
        return stored
''',
)
replace_once(
    "src/app/agent_runtime/task_graph_repository.py",
    '''        old_ids = {
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT node_id
                  FROM omnix_task_graph_node_runs
                 WHERE workspace_id = %s AND run_id = %s
                """,
                (self.context.workspace_id, run_id),
            ).fetchall()
        }
        new_ids = {node.id for node in graph.nodes}
        removed = old_ids - new_ids
''',
    '''        existing_rows = self.connection.execute(
            """
            SELECT node_id, status, fingerprint, child_run_id
              FROM omnix_task_graph_node_runs
             WHERE workspace_id = %s AND run_id = %s
            """,
            (self.context.workspace_id, run_id),
        ).fetchall()
        old_ids = {str(row[0]) for row in existing_rows}
        new_ids = {node.id for node in graph.nodes}
        new_fingerprints = {
            node.id: task_node_fingerprint(node)
            for node in graph.nodes
        }
        revoked_child_runs = self._revoke_agent_runs(
            [
                str(row[3])
                for row in existing_rows
                if row[3]
                and str(row[1]) in {
                    "ready",
                    "running",
                    "waiting_for_approval",
                }
                and not (
                    str(row[0]) in reusable_node_ids
                    and str(row[0]) in new_ids
                    and str(row[2]) == new_fingerprints[str(row[0])]
                )
            ],
            reason=(
                f"task_graph_revision_revoked:{run_id}:"
                f"revision:{graph.revision}"
            ),
        )
        removed = old_ids - new_ids
''',
)
replace_once(
    "src/app/agent_runtime/task_graph_repository.py",
    '''                    "graph_revision": graph.revision,
                    "reused_nodes": sorted(reusable_node_ids),
                    "removed_nodes": sorted(removed),
                },
''',
    '''                    "graph_revision": graph.revision,
                    "reused_nodes": sorted(reusable_node_ids),
                    "removed_nodes": sorted(removed),
                    "revoked_child_runs": revoked_child_runs,
                },
''',
)

# Keep the coverage-count regression about count semantics rather than publisher trust.
replace_once(
    "src/tests/agent_runtime/test_evidence_coverage.py",
    '''            _requirement("react", "React").model_copy(update={"minimum_matches": 2}),
            _requirement("vue", "Vue").model_copy(update={"minimum_matches": 2}),
''',
    '''            _requirement("react", "React", trust="reputable").model_copy(update={"minimum_matches": 2}),
            _requirement("vue", "Vue", trust="reputable").model_copy(update={"minimum_matches": 2}),
''',
)

Path("src/tests/agent_runtime/test_review_fixes_round2.py").write_text(r'''from __future__ import annotations

import pytest

from app.agent_runtime.contracts import (
    EvidenceCoverage,
    EvidencePolicy,
    EvidenceRequirement,
    EvidenceSourceOption,
    ModelRef,
)
from app.agent_runtime.evidence import build_evidence_receipt, evaluate_evidence_set
from app.agent_runtime.semantic_task import (
    SemanticDataDependency,
    SemanticOperation,
    SemanticTask,
)
from app.agent_runtime.task_graph import TaskEdge, TaskGraph, TaskNode, compile_task_graph
from app.assistant_tools.repo_adapter import GitHubCliRuntimeAdapter


MODEL = ModelRef(provider_id="test", model_id="test-model")


def _release_policy() -> EvidencePolicy:
    requirement = EvidenceRequirement(
        id="react-release",
        source_class="software_release",
        coverage=EvidenceCoverage(
            kind="software_package",
            coverage_key="software_package:react",
        ),
        freshness="timeless",
        trust_floor="primary",
        fallback_policy="allow_fallback",
        acceptable_sources=[
            EvidenceSourceOption(
                source_class="software_release",
                trust_floor="primary",
                preference=0,
            )
        ],
    )
    return EvidencePolicy(requirement="required", requirements=[requirement])


def _web_receipt(*, url: str, title: str, snippet: str):
    return build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=_release_policy(),
        capability_id="research.web_search",
        request_input={"query": "React stable release"},
        result_payload={
            "output": {
                "items": [
                    {
                        "url": url,
                        "title": title,
                        "snippet": snippet,
                        "metadata": {"query": "React stable release"},
                    }
                ]
            }
        },
        error=None,
        requirement_id="react-release",
        source_class_hint="software_release",
    )


def test_fallback_result_title_and_metadata_cannot_prove_query_subject() -> None:
    receipt = _web_receipt(
        url="https://example.com/unrelated",
        title="React stable release",
        snippet="An unrelated project published a new version.",
    )
    assert receipt is not None
    assert receipt.coverage == []


def test_arbitrary_github_repository_is_not_primary_release_evidence() -> None:
    receipt = _web_receipt(
        url="https://github.com/example/react/releases/tag/v99",
        title="React v99",
        snippet="React published version 99.",
    )
    assert receipt is not None
    assert receipt.trust_level == "reputable"
    evidence = evaluate_evidence_set("run-1", _release_policy(), [receipt])
    assert evidence.passed is False
    assert evidence.requirements[0].status == "insufficient_trust"


def test_known_upstream_github_repository_can_be_primary_release_evidence() -> None:
    receipt = _web_receipt(
        url="https://github.com/facebook/react/releases/tag/v20.0.0",
        title="React v20",
        snippet="React published version 20.0.0.",
    )
    assert receipt is not None
    assert receipt.trust_level == "primary"
    assert evaluate_evidence_set("run-1", _release_policy(), [receipt]).passed is True


def test_dependency_only_read_precedes_explicit_read_consumer() -> None:
    task = SemanticTask(
        intent="read filing then research release",
        operations=[
            SemanticOperation(
                kind="research",
                target="software_release",
                subject_reference="React",
            )
        ],
        data_dependencies=[
            SemanticDataDependency(
                target="market_filing",
                subject_reference="GME",
                freshness="current",
                retrieval_mode="lookup",
            )
        ],
        autonomous=True,
        multi_step=True,
        ambiguity="none",
    )
    compiled = compile_task_graph(
        "Use the current GME filing context, then research the React release.",
        task,
        model=MODEL,
    )
    assert compiled.ok is True
    assert compiled.graph is not None
    trading = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "trading-research"
    )
    research = next(
        node for node in compiled.graph.nodes
        if node.profile_id == "research"
    )
    assert any(
        edge.source == trading.id
        and edge.target == research.id
        and edge.kind == "data"
        for edge in compiled.graph.edges
    )


def test_capability_node_requires_exact_explicit_broker_authority() -> None:
    with pytest.raises(ValueError, match="explicitly issue exactly"):
        TaskNode(
            id="ci",
            kind="capability",
            capability_id="github.inspect_ci",
            input_template={"repository": "autonomx/omnix", "ref": "main"},
        )

    node = TaskNode(
        id="ci",
        kind="capability",
        capability_id="github.inspect_ci",
        required_external_capabilities=["github.inspect_ci"],
        input_template={"repository": "autonomx/omnix", "ref": "main"},
    )
    assert node.required_external_capabilities == ["github.inspect_ci"]


def test_capability_node_cannot_consume_predecessor_data() -> None:
    source = TaskNode(id="source", kind="join", objective="source")
    capability = TaskNode(
        id="ci",
        kind="capability",
        capability_id="github.inspect_ci",
        required_external_capabilities=["github.inspect_ci"],
        input_template={"repository": "autonomx/omnix", "ref": "main"},
    )
    with pytest.raises(ValueError, match="cannot consume predecessor data"):
        TaskGraph(
            user_request_digest="request",
            nodes=[source, capability],
            edges=[
                TaskEdge(
                    source="source",
                    target="ci",
                    kind="data",
                    target_input="repository",
                )
            ],
        )


def test_ci_adapter_resolves_immutable_sha_and_paginates_all_status_surfaces() -> None:
    adapter = object.__new__(GitHubCliRuntimeAdapter)
    adapter.timeout = 30.0
    commit_sha = "a" * 40
    calls: list[str] = []

    def fake_gh(args, *, timeout=None):
        del timeout
        endpoint = str(args[-1])
        calls.append(endpoint)
        if endpoint == "repos/autonomx/omnix/commits/main":
            return {"sha": commit_sha}
        if "check-runs?per_page=100&page=1" in endpoint:
            return {
                "total_count": 101,
                "check_runs": [
                    {
                        "id": index,
                        "name": f"check-{index}",
                        "status": "completed",
                        "conclusion": "success",
                        "app": {"slug": "actions"},
                    }
                    for index in range(1, 101)
                ],
            }
        if "check-runs?per_page=100&page=2" in endpoint:
            return {
                "total_count": 101,
                "check_runs": [
                    {
                        "id": 101,
                        "name": "check-101",
                        "status": "completed",
                        "conclusion": "success",
                        "app": {"slug": "actions"},
                    }
                ],
            }
        if "statuses?per_page=100&page=1" in endpoint:
            return [{"context": "legacy/status", "state": "success"}]
        raise AssertionError(endpoint)

    adapter._gh = fake_gh
    result = adapter.inspect_ci(repository="autonomx/omnix", ref="main")
    assert result["requested_ref"] == "main"
    assert result["resolved_commit"] == commit_sha
    assert result["checks_passed"] is True
    assert len(result["checks"]) == 101
    assert any("check-runs?per_page=100&page=2" in call for call in calls)
    assert result["statuses"] == [
        {"context": "legacy/status", "state": "success", "description": None}
    ]


def test_ci_adapter_does_not_treat_neutral_as_success() -> None:
    adapter = object.__new__(GitHubCliRuntimeAdapter)
    adapter.timeout = 30.0

    def fake_gh(args, *, timeout=None):
        del timeout
        endpoint = str(args[-1])
        if endpoint.endswith("/commits/main"):
            return {"sha": "b" * 40}
        if "check-runs?" in endpoint:
            return {
                "total_count": 1,
                "check_runs": [
                    {
                        "id": 1,
                        "name": "required",
                        "status": "completed",
                        "conclusion": "neutral",
                        "app": {"slug": "actions"},
                    }
                ],
            }
        if "statuses?" in endpoint:
            return []
        raise AssertionError(endpoint)

    adapter._gh = fake_gh
    result = adapter.inspect_ci(repository="autonomx/omnix", ref="main")
    assert result["checks_passed"] is False
''', encoding="utf-8")

Path("src/tests/persistence/test_task_graph_authority_revocation_integration.py").write_text(r'''from __future__ import annotations

import os
import uuid

import pytest

from app.agent_runtime.contracts import AgentRunSpec, ModelRef
from app.agent_runtime.repository import PostgresAgentRunRepository
from app.agent_runtime.task_graph import TaskGraph, TaskNode, task_node_fingerprint
from app.agent_runtime.task_graph_repository import PostgresTaskGraphRepository
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.unit_of_work import unit_of_work


pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
MODEL = ModelRef(provider_id="test", model_id="test-model")


def _database() -> PostgresDatabase:
    return PostgresDatabase(
        DatabaseSettings(
            url=os.environ["OMNIX_TEST_DATABASE_URL"],
            pool_min=1,
            pool_max=3,
            connect_timeout_seconds=10,
            statement_timeout_ms=30_000,
            application_name="omnix-task-graph-revocation-tests",
        )
    )


def _create_running_child(repository: PostgresAgentRunRepository, run_id: str) -> None:
    snapshot = repository.create_run(
        AgentRunSpec(
            run_id=run_id,
            task="Research only.",
            objective="Research only.",
            profile="research",
            model=MODEL,
        )
    )
    repository.update_state(
        run_id,
        expected_revision=snapshot.revision,
        status="running",
    )


def test_revision_revokes_invalidated_child_before_current_identity_is_cleared() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        graph_run_id = f"graph-{uuid.uuid4().hex}"
        child_run_id = f"child-{uuid.uuid4().hex}"
        node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research the original target.",
            model=MODEL,
        )
        graph = TaskGraph(
            graph_id=f"graph-contract-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="v1",
            nodes=[node],
        )
        with unit_of_work(database) as work:
            graph_repository = PostgresTaskGraphRepository(work.connection, context)
            agent_repository = PostgresAgentRunRepository(work.connection, context)
            graph_repository.create_run(graph, run_id=graph_run_id)
            _create_running_child(agent_repository, child_run_id)
            claimed = graph_repository.claim_node(
                graph_run_id,
                node.id,
                child_run_id=child_run_id,
                expected_fingerprint=task_node_fingerprint(node),
                expected_graph_revision=1,
            )
            assert claimed is not None
            work.commit()

        revised_node = node.model_copy(update={"objective": "Research a different target."})
        revised_graph = graph.model_copy(
            update={"revision": 2, "user_request_digest": "v2", "nodes": [revised_node]}
        )
        with unit_of_work(database) as work:
            graph_repository = PostgresTaskGraphRepository(work.connection, context)
            agent_repository = PostgresAgentRunRepository(work.connection, context)
            graph_repository.apply_revision(
                graph_run_id,
                revised_graph,
                user_instruction="Use the different target.",
                reusable_node_ids=set(),
            )
            child = agent_repository.get_run(child_run_id)
            assert child is not None
            assert child.status == "cancel_requested"
            assert child.desired_state == "cancelled"
            current = graph_repository.get_run(graph_run_id)
            assert current is not None
            state = next(item for item in current.node_states if item.node_id == node.id)
            assert state.child_run_id is None
            work.commit()
    finally:
        database.close()


def test_node_cancellation_revokes_child_authority_before_process_cleanup() -> None:
    database = _database()
    try:
        context = bootstrap_local_tenant(database)
        graph_run_id = f"graph-{uuid.uuid4().hex}"
        child_run_id = f"child-{uuid.uuid4().hex}"
        node = TaskNode(
            id="research",
            kind="agent",
            profile_id="research",
            objective="Research target.",
            model=MODEL,
        )
        graph = TaskGraph(
            graph_id=f"graph-contract-{uuid.uuid4().hex}",
            revision=1,
            user_request_digest="request",
            nodes=[node],
        )
        with unit_of_work(database) as work:
            graph_repository = PostgresTaskGraphRepository(work.connection, context)
            agent_repository = PostgresAgentRunRepository(work.connection, context)
            graph_repository.create_run(graph, run_id=graph_run_id)
            _create_running_child(agent_repository, child_run_id)
            claimed = graph_repository.claim_node(
                graph_run_id,
                node.id,
                child_run_id=child_run_id,
                expected_fingerprint=task_node_fingerprint(node),
                expected_graph_revision=1,
            )
            assert claimed is not None
            cancelled = graph_repository.update_node(
                graph_run_id,
                node.id,
                status="cancelled",
                last_error="cancelled_by_user",
                expected_fingerprint=claimed.fingerprint,
                expected_child_run_id=child_run_id,
                match_child_run_id=True,
                expected_statuses=("ready",),
                expected_graph_revision=1,
            )
            assert cancelled is not None
            child = agent_repository.get_run(child_run_id)
            assert child is not None
            assert child.status == "cancel_requested"
            assert child.desired_state == "cancelled"
            work.commit()
    finally:
        database.close()
''', encoding="utf-8")

replace_once(
    "docs/agent-runtime/task-graph-phases-15-19.md",
    "Revise recompiles and replaces the current graph shape. Changed/removed running children are cancelled.\n",
    "Revise recompiles and replaces the current graph shape. Changed/removed running children have their durable Agent authority revoked transactionally with graph invalidation (`desired_state=cancelled`) before their current node identity is cleared; process abort is best-effort cleanup rather than the authority boundary.\n",
)
replace_once(
    "docs/agent-runtime/task-graph-phases-15-19.md",
    "Dependency edges delay only consumers. An authority-free join performs fan-in.\n",
    "Dependency edges delay only consumers. Dependency-only profile reads are conservatively ordered before explicit cross-profile consumers, including read consumers, until semantic dependencies carry typed producer/consumer IDs. An authority-free join performs fan-in.\n",
)
replace_once(
    "docs/agent-runtime/task-graph-phases-15-19.md",
    "The coordinator owns none of those capabilities.\n",
    "The coordinator owns none of those capabilities. Reserved direct capability nodes are fixed-input, broker-only primitives: they must explicitly issue exactly one capability and cannot consume predecessor data until a governed dynamic-input binding contract exists.\n",
)
