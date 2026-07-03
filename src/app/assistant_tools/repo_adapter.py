"""Repository runtime adapter foundation for assistant tools."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from .models import AssistantToolRequest, AssistantToolResult


@dataclass(frozen=True)
class RepositoryPullRequestRecord:
    number: int
    title: str
    head_sha: str
    checks_passed: bool = False
    merged: bool = False


class RepositoryRuntimeAdapter(Protocol):
    def read_repo(self, *, repository: str) -> dict[str, object]: ...

    def create_branch(self, *, repository: str, branch: str, base_sha: str) -> dict[str, object]: ...

    def create_pr(self, *, repository: str, title: str, body: str, branch: str, base: str) -> RepositoryPullRequestRecord: ...

    def merge_pr(self, *, repository: str, number: int, expected_head_sha: str) -> RepositoryPullRequestRecord: ...


@dataclass
class FakeRepositoryRuntimeAdapter:
    pull_requests: dict[int, RepositoryPullRequestRecord] = field(default_factory=dict)

    def read_repo(self, *, repository: str) -> dict[str, object]:
        return {"repository": repository, "status": "readable", "pull_request_count": len(self.pull_requests)}

    def create_branch(self, *, repository: str, branch: str, base_sha: str) -> dict[str, object]:
        return {"repository": repository, "branch": branch, "base_sha": base_sha, "created": True}

    def create_pr(self, *, repository: str, title: str, body: str, branch: str, base: str) -> RepositoryPullRequestRecord:
        number = max(self.pull_requests.keys(), default=1000) + 1
        record = RepositoryPullRequestRecord(number=number, title=title, head_sha=f"fake-{uuid.uuid4().hex[:12]}")
        self.pull_requests[number] = record
        return record

    def merge_pr(self, *, repository: str, number: int, expected_head_sha: str) -> RepositoryPullRequestRecord:
        record = self.pull_requests.get(number)
        if record is None:
            record = RepositoryPullRequestRecord(number=number, title="Existing pull request", head_sha=expected_head_sha, checks_passed=True)
        if record.head_sha != expected_head_sha:
            raise ValueError("head_sha_mismatch")
        if not record.checks_passed:
            raise ValueError("checks_not_passed")
        merged = RepositoryPullRequestRecord(number=record.number, title=record.title, head_sha=record.head_sha, checks_passed=True, merged=True)
        self.pull_requests[number] = merged
        return merged


_DEFAULT_REPOSITORY_ADAPTER = FakeRepositoryRuntimeAdapter(
    pull_requests={1: RepositoryPullRequestRecord(number=1, title="Prepared change", head_sha="abc123", checks_passed=True)}
)


def get_repository_runtime_adapter() -> RepositoryRuntimeAdapter:
    return _DEFAULT_REPOSITORY_ADAPTER


def run_repository_tool_request(request: AssistantToolRequest, adapter: RepositoryRuntimeAdapter | None = None) -> AssistantToolResult:
    runtime = adapter or get_repository_runtime_adapter()
    repository = str(request.input.get("repository") or request.input.get("repo") or "")
    try:
        if request.action_id == "github.read_repo":
            output = runtime.read_repo(repository=repository)
            return AssistantToolResult(
                tool_id=request.tool_id,
                action_id=request.action_id,
                session_id=request.session_id,
                risk_level="low",
                state_changed=False,
                result_summary=f"Read repository {repository or 'metadata'}.",
                output=output,
            )
        if request.action_id == "github.create_branch":
            output = runtime.create_branch(
                repository=repository,
                branch=str(request.input.get("branch") or ""),
                base_sha=str(request.input.get("base_sha") or ""),
            )
            return AssistantToolResult(
                tool_id=request.tool_id,
                action_id=request.action_id,
                session_id=request.session_id,
                risk_level="medium",
                state_changed=True,
                result_summary=f"Created repository branch {output.get('branch')}.",
                output=output,
            )
        if request.action_id == "github.create_pr":
            record = runtime.create_pr(
                repository=repository,
                title=str(request.input.get("title") or "Prepared change"),
                body=str(request.input.get("body") or ""),
                branch=str(request.input.get("branch") or ""),
                base=str(request.input.get("base") or ""),
            )
            return AssistantToolResult(
                tool_id=request.tool_id,
                action_id=request.action_id,
                session_id=request.session_id,
                risk_level="medium",
                state_changed=True,
                result_summary=f"Opened pull request #{record.number}.",
                output={"pull_request": record.__dict__},
            )
        if request.action_id == "github.merge_pr":
            record = runtime.merge_pr(
                repository=repository,
                number=int(request.input.get("number") or 0),
                expected_head_sha=str(request.input.get("expected_head_sha") or ""),
            )
            return AssistantToolResult(
                tool_id=request.tool_id,
                action_id=request.action_id,
                session_id=request.session_id,
                risk_level="high",
                state_changed=True,
                result_summary=f"Merged pull request #{record.number}.",
                output={"pull_request": record.__dict__},
            )
    except ValueError as exc:
        return AssistantToolResult(
            tool_id=request.tool_id,
            action_id=request.action_id,
            session_id=request.session_id,
            error=str(exc),
            result_summary="Repository action was blocked by runtime safeguards.",
        )
    return AssistantToolResult(
        tool_id=request.tool_id,
        action_id=request.action_id,
        session_id=request.session_id,
        error="repository_action_not_available",
    )
