from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"missing regression-fix anchor in {path}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def replace_regex(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count == 0:
        if replacement[:80] in text:
            return
        raise RuntimeError(f"missing regression-fix regex anchor in {path}: {pattern[:120]!r}")
    write(path, updated)


# The public pi_runtime wrapper already exposes omnix_plan only for mutating
# coding-quality runs. Do not widen that authority in the stable core merely
# because RunChangeSet adds another extension tool.
replace_once(
    "src/app/agent_runtime/pi_runtime_core.py",
    '''    if "workspace.run_change_set" in spec.capabilities:\n        tools.add("omnix_change_set")\n    if spec.profile == "coding":\n        tools.add("omnix_plan")\n''',
    '''    if "workspace.run_change_set" in spec.capabilities:\n        tools.add("omnix_change_set")\n''',
)

# Server authority is derived from requirement state and authoritative finding
# attribution. A reviewer may say changes_required because it noticed a
# baseline-only issue, but that advisory verdict cannot override Omnix's subject
# binding. "blocked" remains a hard protocol/runtime outcome.
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict != "approve":\n        return False\n''',
    '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict == "blocked":\n        return False\n''',
)

# Candidate validation authority is the latest execution for each validation
# obligation on the exact candidate. An older pass cannot hide a later failure.
replace_once(
    "src/app/agent_runtime/coding_quality.py",
    '''        matching = [item for item in rows if item.validation_id == expected.id]\n        if any(item.outcome == "passed" and item.success for item in matching):\n            continue\n        if not matching:\n            missing.append(expected)\n            continue\n        latest = max(matching, key=lambda item: (item.finished_at, item.result_id))\n        if latest.outcome in {"infrastructure_failure", "protocol_failure"}:\n''',
    '''        matching = [item for item in rows if item.validation_id == expected.id]\n        if not matching:\n            missing.append(expected)\n            continue\n        latest = max(matching, key=lambda item: (item.finished_at, item.result_id))\n        if latest.outcome == "passed" and latest.success:\n            continue\n        if latest.outcome in {"infrastructure_failure", "protocol_failure"}:\n''',
)

# Convergence history must survive runs with more than 5,000 events; otherwise
# a long run could accidentally forget an earlier repair/retry obligation and
# re-authorize the same candidate. Page the durable stream instead of truncating.
replace_once(
    "src/app/agent_runtime/service.py",
    '''def _quality_events(repository: PostgresAgentRunRepository, run_id: str) -> list[AgentEvent]:\n    return repository.list_events(run_id, after_sequence=0, limit=5000)\n''',
    '''def _quality_events(repository: PostgresAgentRunRepository, run_id: str) -> list[AgentEvent]:\n    events: list[AgentEvent] = []\n    after_sequence = 0\n    page_size = 1000\n    while True:\n        page = repository.list_events(run_id, after_sequence=after_sequence, limit=page_size)\n        if not page:\n            break\n        events.extend(page)\n        next_sequence = max(int(item.sequence or after_sequence) for item in page)\n        if next_sequence <= after_sequence:\n            break\n        after_sequence = next_sequence\n        if len(page) < page_size:\n            break\n    return events\n''',
)

# Infrastructure/protocol retries are bounded by CandidateKey + validation_id,
# not by the exact error text. Different timeout/error strings cannot reset the
# retry allowance for the same validation obligation on the same candidate.
replace_regex(
    "src/app/agent_runtime/service.py",
    r'''    def _request_validation_retry\(\n.*?\n    def _request_validation_repair\(''',
    '''    def _request_validation_retry(\n        self,\n        repository: PostgresAgentRunRepository,\n        current: AgentRunSnapshot,\n        revision: TaskRevision,\n        *,\n        attempt: int,\n        workspace_state_id: str,\n        failures,\n    ) -> tuple | None:\n        validation_ids = sorted({item.validation_id for item in failures})\n        failure_fingerprint = _validation_failure_fingerprint(failures)\n        prior_events = [\n            event for event in _quality_events(repository, current.run_id)\n            if event.event_type == "quality.validation_retry_requested"\n            and str(event.payload.get("task_revision_id") or "") == revision.revision_id\n            and str(event.payload.get("workspace_state_id") or "") == workspace_state_id\n        ]\n        retry_counts = {\n            validation_id: sum(\n                1 for event in prior_events\n                if validation_id in [str(value) for value in event.payload.get("validation_ids") or []]\n            )\n            for validation_id in validation_ids\n        }\n        limit = _validation_retry_limit()\n        exhausted = sorted(\n            validation_id for validation_id, count in retry_counts.items()\n            if count >= limit\n        )\n        if exhausted:\n            repository.append_event(AgentEvent(\n                run_id=current.run_id,\n                event_type="quality.validation_retry_exhausted",\n                payload={\n                    "task_revision_id": revision.revision_id,\n                    "workspace_state_id": workspace_state_id,\n                    "failure_fingerprint": failure_fingerprint,\n                    "validation_ids": validation_ids,\n                    "exhausted_validation_ids": exhausted,\n                    "retry_limit": limit,\n                },\n            ))\n            return self._quality_fail(repository, current, "quality_failed:validation_retry_exhausted")\n        retry = max(retry_counts.values(), default=0) + 1\n        retry_identity = hashlib.sha256(\n            "|".join(validation_ids).encode("utf-8")\n        ).hexdigest()[:24]\n        repository.append_event(AgentEvent(\n            run_id=current.run_id,\n            event_type="quality.validation_retry_requested",\n            payload={\n                "task_revision_id": revision.revision_id,\n                "workspace_state_id": workspace_state_id,\n                "fingerprint": retry_identity,\n                "failure_fingerprint": failure_fingerprint,\n                "retry": retry,\n                "retry_limit": limit,\n                "validation_ids": validation_ids,\n            },\n        ))\n        missing = [\n            spec for spec in revision.validation_plan\n            if spec.required and spec.id in set(validation_ids)\n        ]\n        prompt = validation_prompt(revision, missing)\n        prompt += "\\n\\nThis is a bounded same-candidate infrastructure/protocol validation retry. Do not claim completion until it executes normally."\n        return self._queue_quality_resume(\n            repository,\n            run_id=current.run_id,\n            prompt=prompt,\n            idempotency_key=f"quality-validation-retry:{current.run_id}:{revision.revision_id}:{workspace_state_id}:{retry_identity}:{retry}",\n            quality_stage="validating",\n            quality_attempt=attempt,\n            task_revision_id=revision.revision_id,\n            workspace_state_id=workspace_state_id,\n        )\n\n    def _request_validation_repair(''',
)

# Existing quality fixtures manually construct a coding RunSpec rather than
# resolving the profile. Keep the fixture authority aligned with the now-issued
# read-only RunChangeSet capability used by independent review.
replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    '''            "workspace.git_diff",\n            "workspace.edit",\n''',
    '''            "workspace.git_diff",\n            "workspace.run_change_set",\n            "workspace.edit",\n''',
)
replace_once(
    "src/tests/agent_runtime/test_coding_quality_phases_20_31.py",
    '''        "workspace.git_diff",\n    }\n''',
    '''        "workspace.git_diff",\n        "workspace.run_change_set",\n    }\n''',
)

# The old blob-store regression asserted the retired workspace.diff name and a
# fake WorkspaceAuthority surface that predates canonical tracked/untracked
# RunChangeSet capture. Preserve the intent: the authoritative patch is durable
# in the blob store, not a machine-local temp file.
replace_once(
    "src/tests/agent_runtime/test_acceptance_authority.py",
    '''        def git_diff(self, paths=None) -> str:\n            assert paths == ["a.txt"]\n            return "diff --git a/a.txt b/a.txt\\n+changed\\n"\n''',
    '''        def git_status_entries(self):\n            return {"a.txt": " M"}\n\n        def git_head(self):\n            return "abc123"\n\n        def git_tracked_diff(self, paths=None) -> str:\n            assert paths == ["a.txt"]\n            return "diff --git a/a.txt b/a.txt\\n+changed\\n"\n\n        def git_diff(self, paths=None) -> str:\n            assert paths == ["a.txt"]\n            return "diff --git a/a.txt b/a.txt\\n+changed\\n"\n''',
)
replace_once(
    "src/tests/agent_runtime/test_acceptance_authority.py",
    '''    assert service.blob_store.storage_key.endswith("/workspace.diff")\n''',
    '''    assert service.blob_store.storage_key.endswith("/run-owned.patch")\n''',
)

# Provenance tests now inspect the canonical diff artifact rather than the
# retired workspace.diff alias. The assertions about run-owned paths and
# baseline conflicts remain unchanged.
path = "src/tests/agent_runtime/test_service_workspace_provenance.py"
text = read(path)
text = text.replace('item.name == "workspace.diff"', 'item.name == "run-change-set.patch"')
write(path, text)

# Strengthen the new convergence matrix: a reviewer-declared changes_required
# verdict cannot make a baseline-only high finding blocking after server
# attribution, and a later same-candidate failure supersedes an earlier pass.
path = "src/tests/agent_runtime/test_candidate_authority_convergence.py"
text = read(path)
if "test_baseline_only_changes_required_verdict_is_nonblocking_after_server_attribution" not in text:
    text += '''\n\ndef test_baseline_only_changes_required_verdict_is_nonblocking_after_server_attribution() -> None:\n    snapshot = ReviewSnapshot(\n        run_id="run-1", task_revision_id="rev-1", workspace_state_id="state-1",\n        base_commit_sha="abc", patch_checksum="def", run_change_set_id="cs-1",\n        workspace_root="/tmp/review", subject_paths=["src/styles.css"], context_paths=["src/repository.py"],\n    )\n    result = parse_review_result(\n        '{"verdict":"changes_required","requirements":[{"requirement_id":"R","status":"satisfied","evidence":"ok"}],"findings":[{"severity":"high","category":"correctness","file":"src/repository.py","location":null,"problem":"baseline issue","recommended_fix":null,"subject_paths":[],"context_paths":["src/repository.py"]}],"missing_tests":[],"residual_risks":[]}',\n        parent_run_id="run-1", reviewer_run_id="reviewer", snapshot=snapshot,\n    )\n    assert result.findings[0].attribution == "baseline_context"\n    assert result.findings[0].blocking is False\n    assert review_is_acceptable(result, _revision())\n\n\ndef test_latest_same_candidate_validation_result_is_authoritative() -> None:\n    revision = _revision()\n    passed = _validation("passed", digest="pass")\n    failed = _validation("substantive_failure", digest="fail").model_copy(\n        update={"finished_at": passed.finished_at.replace(microsecond=min(999999, passed.finished_at.microsecond + 1))}\n    )\n    gate, rows = candidate_validation_gate(revision, [passed, failed], workspace_state_id="state-1")\n    assert gate == "validation_repair"\n    assert rows and rows[0].output_digest == "fail"\n'''
    write(path, text)

print("candidate authority regression fixes applied")
