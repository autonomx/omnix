from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.assistant_memory import resolve_chat_scope
from app.assistant_memory.service import (
    LegacyMemoryReadOnlyError,
    default_memory_service,
)
from app.assistant_memory_v2 import (
    MemoryGrant,
    MemorySpaceKey,
    RetrievalCandidate,
    RetrievalResult,
    RetrievalScore,
)
from app.chat import memory_prompt
from app.chat.prompt_assembly import PromptAssembly, PromptMemoryItem, PromptTurn
from app.chat.prompt_rendering import _memory_section

NOW = datetime(2026, 9, 14, 3, 0, tzinfo=timezone.utc)


def _session(*, read_memory: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id="session:v2-prompt",
        profile_id="profile:alice",
        workspace_id="workspace:default",
        project_id="project:omnix",
        interaction_mode="character",
        character_id="sofia",
        read_memory=read_memory,
        memory_enabled=True,
        memory_snapshot_id=None,
        memory_snapshot_revision=None,
        shared_memory_access="read_only",
        messages=(SimpleNamespace(role="user", content="What game do I like?"),),
    )


def _candidate(*, shared: bool = False) -> RetrievalCandidate:
    reasons = ("active_graph_assertion",)
    if shared:
        reasons = (*reasons, "memory_grant:grant:system", "federated_source:system:system-assistant")
    return RetrievalCandidate(
        ref_id="assertion:favorite-game",
        item_type="assertion",
        domain="preference",
        content="profile:alice favorite game Skyrim",
        scores=RetrievalScore(semantic=1.0, composite=1.0),
        reasons=reasons,
        evidence_observation_ids=("obs:1",),
    )


def _result(candidate: RetrievalCandidate) -> RetrievalResult:
    return RetrievalResult(
        query_id="q:v2",
        candidates=(candidate,),
        dynamic_context=(candidate.content,),
        token_estimate=8,
        observation_watermark=4,
        graph_revision=3,
        index_graph_revision=3,
        elapsed_ms=1.0,
        deadline_ms=50.0,
    )


class _Runtime:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.queries = []
        self.epoch = SimpleNamespace(epoch=2, authority="v2")
        self.grant_store = SimpleNamespace(active_for_target=lambda _space: [])

    def current(self):
        return SimpleNamespace(epoch=self.epoch)

    def assert_v2_authoritative(self):
        return SimpleNamespace(epoch=self.epoch)

    def retrieve(self, query):
        self.queries.append(query)
        return self.result


def test_v2_authority_bypasses_legacy_snapshot_and_service(monkeypatch) -> None:
    runtime = _Runtime(_result(_candidate()))
    monkeypatch.setattr(memory_prompt, "chat_memory_enabled", lambda: True)
    monkeypatch.setattr(memory_prompt, "resolve_shared_memory_categories", lambda _session: [])

    def legacy_service_must_not_run():
        raise AssertionError("v1 memory service must not be read after v2 cutover")

    items, diagnostics = memory_prompt.resolve_prompt_memory(
        _session(),
        query_text="What game do I like?",
        memory_service_factory=legacy_service_must_not_run,
        memory_v2_runtime_factory=lambda: runtime,
    )

    assert diagnostics["authority"] == "v2"
    assert diagnostics["status"] == "resolved_v2"
    assert diagnostics["snapshot_id"] is None
    assert [item.source for item in items] == ["memory_v2"]
    assert [item.memory_id for item in items] == ["assertion:favorite-game"]
    query = runtime.queries[0]
    assert query.space == MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id="sofia",
    )
    assert query.text == "What game do I like?"
    assert {(scope.kind, scope.scope_id) for scope in query.visible_scopes} == {
        ("global", "profile:alice"),
        ("workspace", "workspace:default"),
        ("project", "project:omnix"),
        ("session", "session:v2-prompt"),
    }


def test_federated_candidate_is_labeled_read_only_shared_v2(monkeypatch) -> None:
    runtime = _Runtime(_result(_candidate(shared=True)))
    runtime.grant_store = SimpleNamespace(
        active_for_target=lambda _space: [SimpleNamespace(grant_id="grant:system")]
    )
    monkeypatch.setattr(memory_prompt, "chat_memory_enabled", lambda: True)
    monkeypatch.setattr(
        memory_prompt,
        "resolve_shared_memory_categories",
        lambda _session: ["fact"],
    )

    items, diagnostics = memory_prompt.resolve_prompt_memory(
        _session(),
        memory_v2_runtime_factory=lambda: runtime,
    )

    assert [item.source for item in items] == ["shared_memory_v2"]
    assert diagnostics["shared_selected_memory_ids"] == ["assertion:favorite-game"]
    assert runtime.queries[0].grant_ids == ("grant:system",)


def test_shared_only_v2_path_never_queries_target_local_memory(monkeypatch) -> None:
    target = MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="character",
        owner_id="sofia",
    )
    source = MemorySpaceKey(
        principal_id="profile:alice",
        owner_type="system",
        owner_id="system-assistant",
    )
    grant = MemoryGrant(
        grant_id="grant:system",
        source_space=source,
        target_space=target,
        allowed_domains=("fact", "preference"),
        created_by="test",
        created_at=NOW,
    )
    source_candidate = RetrievalCandidate(
        ref_id="assertion:shared",
        item_type="assertion",
        domain="fact",
        content="Shared system fact",
        scores=RetrievalScore(composite=0.9),
        evidence_observation_ids=("obs:shared",),
    )
    source_result = RetrievalResult(
        query_id="source:q",
        candidates=(source_candidate,),
        dynamic_context=(source_candidate.content,),
        token_estimate=5,
        observation_watermark=2,
        graph_revision=2,
        index_graph_revision=2,
        elapsed_ms=1.0,
        deadline_ms=50.0,
    )
    runtime = _Runtime(source_result)
    runtime.retrieve = lambda _query: (_ for _ in ()).throw(
        AssertionError("target-local federated retrieve must not run when local reads are disabled")
    )
    runtime.grant_store = SimpleNamespace(active_for_target=lambda _space: [grant])
    runtime.local_retriever = SimpleNamespace(retrieve=lambda query: source_result)
    runtime.graph_store = SimpleNamespace(state=lambda _space: SimpleNamespace(graph_revision=3))
    runtime.observation_store = SimpleNamespace(watermark=lambda _space: 4)
    runtime.search_index = SimpleNamespace(index_graph_revision=lambda _space: 3)
    monkeypatch.setattr(memory_prompt, "chat_memory_enabled", lambda: True)
    monkeypatch.setattr(
        memory_prompt,
        "resolve_shared_memory_categories",
        lambda _session: ["fact"],
    )

    items, diagnostics = memory_prompt.resolve_prompt_memory(
        _session(read_memory=False),
        memory_v2_runtime_factory=lambda: runtime,
    )

    assert [item.memory_id for item in items] == ["assertion:shared"]
    assert [item.source for item in items] == ["shared_memory_v2"]
    assert diagnostics["selected_memory_count"] == 1


def test_renderer_does_not_call_derived_v2_memory_user_approved() -> None:
    assembly = PromptAssembly(
        approved_memory=[
            PromptMemoryItem(
                memory_id="assertion:local",
                content="A derived preference",
                scope="retrieved",
                category="preference",
                revision=1,
                source="memory_v2",
            ),
            PromptMemoryItem(
                memory_id="assertion:shared",
                content="A federated fact",
                scope="retrieved",
                category="fact",
                revision=1,
                source="shared_memory_v2",
            ),
        ],
        current_user_message=PromptTurn(role="user", content="hello"),
    )

    rendered = _memory_section(assembly)
    assert "Retrieved Memory v2 context follows." in rendered
    assert "Read-only federated Memory v2 context follows." in rendered
    assert "approved for this scope" not in rendered
    assert "revision 1" not in rendered


def test_direct_default_v1_service_is_read_only_after_v2_cutover(monkeypatch) -> None:
    import app.assistant_memory_v2.authority as authority_module
    from app.persistence import runtime_install

    monkeypatch.setattr(runtime_install, "runtime_adapters_installed", lambda: True)
    monkeypatch.setattr(
        authority_module.PostgresMemoryV2AuthorityStore,
        "current",
        lambda _self: SimpleNamespace(epoch=SimpleNamespace(authority="v2")),
    )
    service = default_memory_service()
    context = resolve_chat_scope("session:guard", profile_id="profile:alice")

    with pytest.raises(LegacyMemoryReadOnlyError, match="read-only"):
        service.create_explicit_memory(
            context,
            scope="global",
            category="fact",
            content="This write must be rejected after v2 cutover.",
            provenance_id="message:guard",
        )
