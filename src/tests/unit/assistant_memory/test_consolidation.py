from __future__ import annotations

import pytest

from app.assistant_memory import MemoryService, SQLiteMemoryRepository, resolve_chat_scope
from app.assistant_memory.consolidation import (
    MemoryCapacityPolicy,
    analyze_memory_health,
    supersede_memory,
)
from app.assistant_memory.repository import MemoryConflictError


def setup_service(tmp_path):
    service = MemoryService(SQLiteMemoryRepository(tmp_path / "memory.sqlite3"))
    context = resolve_chat_scope("chat:one", project_id="project:omnix")
    return service, context


def create(service, context, *, content, category="fact", scope="project", pinned=False):
    return service.create_explicit_memory(
        context,
        scope=scope,
        category=category,
        content=content,
        provenance_id=f"msg:{content}",
        pinned=pinned,
    )


def test_health_report_detects_duplicates_contradictions_and_capacity(tmp_path):
    service, context = setup_service(tmp_path)
    create(service, context, content="The provider is LM Studio")
    create(service, context, content="The provider is LM Studio")
    create(service, context, content="The provider is OpenRouter")
    create(service, context, content="Prefer detailed answers", category="preference", pinned=True)

    report = analyze_memory_health(
        service.list_active(context),
        context,
        policy=MemoryCapacityPolicy(
            max_records_per_scope=3,
            soft_token_budget=1,
            hard_token_ceiling=5,
        ),
    )

    assert len(report.duplicate_groups) == 1
    assert report.duplicate_groups[0].normalized_content == "the provider is lm studio"
    assert len(report.contradiction_groups) == 1
    assert report.contradiction_groups[0].subject == "the provider"
    assert report.contradiction_groups[0].values == ["lm studio", "openrouter"]
    assert report.over_record_limit_scopes == ["project:project:omnix"]
    assert report.soft_budget_exceeded is True
    assert report.hard_ceiling_exceeded is True
    assert report.consolidation_required is True


def test_expired_and_untrusted_records_are_reported_but_not_counted_as_prompt_tokens(tmp_path):
    service, context = setup_service(tmp_path)
    expired = create(service, context, content="Temporary fact")
    service.repository.update_record(
        expired.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"}),
        expected_revision=1,
    )
    untrusted = create(service, context, content="Imported fact")
    service.repository.update_record(
        untrusted.model_copy(update={"trust_level": "unverified_import"}),
        expected_revision=1,
    )

    records = service.repository.list_records(scope="project", scope_id="project:omnix")
    report = analyze_memory_health(records, context)

    assert report.expired_memory_ids == [expired.id]
    assert report.untrusted_memory_ids == [untrusted.id]
    assert report.prompt_eligible_token_estimate == 0
    assert report.consolidation_required is True


def test_supersession_is_explicit_revisioned_and_excluded_from_selection(tmp_path):
    service, context = setup_service(tmp_path)
    older = create(service, context, content="The model is alpha")
    replacement = create(service, context, content="The model is beta")

    superseded = supersede_memory(
        service,
        context,
        older_memory_id=older.id,
        replacement_memory_id=replacement.id,
        expected_revision=1,
    )

    assert superseded.status == "superseded"
    assert superseded.revision == 2
    assert superseded.provenance_id == replacement.id
    selected = service.resolve_active_memory(context, token_budget=1000)
    assert [record.id for record in selected.records] == [replacement.id]

    with pytest.raises(MemoryConflictError):
        supersede_memory(
            service,
            context,
            older_memory_id=older.id,
            replacement_memory_id=replacement.id,
            expected_revision=1,
        )


def test_analysis_is_scope_first_and_never_silently_mutates(tmp_path):
    service, context = setup_service(tmp_path)
    other_context = resolve_chat_scope("chat:two", project_id="project:other")
    local = create(service, context, content="The branch is rpg")
    create(service, other_context, content="The branch is main")

    before = service.repository.get_record(local.id)
    report = analyze_memory_health(
        service.repository.list_records(status="active"),
        context,
    )
    after = service.repository.get_record(local.id)

    assert report.visible_record_count == 1
    assert report.contradiction_groups == []
    assert before == after


def test_pinned_records_do_not_bypass_hard_prompt_budget(tmp_path):
    service, context = setup_service(tmp_path)
    create(
        service,
        context,
        content="This pinned record is intentionally much larger than the available prompt budget",
        category="instruction",
        pinned=True,
    )

    selection = service.resolve_active_memory(context, token_budget=2)

    assert selection.records == []
    assert selection.diagnostics.excluded_reason_counts["token_budget"] == 1
    assert selection.diagnostics.truncated is True
