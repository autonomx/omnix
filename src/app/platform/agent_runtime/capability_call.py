"""One broker capability call, as the run's durable state records it.

A call is a row in the run's capability executions. When the capability is an evidence query made under a task
revision, it is also a row in that revision's evidence queries. ``CapabilityCall`` keeps the two together:
``settle`` finishes both, so a refused, rejected, out-of-budget or completed call never leaves its evidence query
open and counted against the revision's budget. The broker (``broker_api``) decides what happens to a call; this
module only records it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from .contracts import AgentApproval
from .evidence import is_evidence_capability

if TYPE_CHECKING:
    from .repository import PostgresAgentRunRepository


@dataclass(frozen=True)
class CapabilityCall:
    run_id: str
    capability_id: str
    execution_key: str
    task_revision_id: str | None = None

    @classmethod
    def open(cls, run_id: str, capability_id: str, execution_key: str, *, task_revision_id: str | None) -> CapabilityCall:
        """An evidence query is scoped to its task revision: the same query asked in a new revision is a new call."""
        call = cls(run_id, capability_id, execution_key, task_revision_id)
        if call.tracks_evidence:
            digest = hashlib.sha256(cast(str, task_revision_id).encode("utf-8")).hexdigest()[:16]
            call = call.under_key(f"{execution_key}:evidence-revision:{digest}")
        return call

    @property
    def tracks_evidence(self) -> bool:
        """Whether the call also holds an evidence query of its task revision."""
        return bool(self.task_revision_id) and is_evidence_capability(self.capability_id)

    def under_key(self, execution_key: str) -> CapabilityCall:
        """The same call under the identity an approval recorded for it."""
        return replace(self, execution_key=execution_key)

    def ensure(self, repository: PostgresAgentRunRepository, *, request_input: dict[str, Any],
               approval_id: str | None) -> dict[str, Any]:
        """The call's execution row, created on the first request."""
        return repository.ensure_capability_execution(
            self.run_id, self.execution_key, self.capability_id, {"input": request_input, "approval_id": approval_id}
        )

    def claim(self, repository: PostgresAgentRunRepository) -> bool:
        return repository.claim_capability_execution(self.run_id, self.execution_key)

    def park_for_approval(self, repository: PostgresAgentRunRepository, approval: AgentApproval | None, *,
                          request_input: dict[str, Any]) -> AgentApproval:
        """Hold the call for a person's decision: one approval per execution key, and the run waits for it."""
        repository.mark_capability_waiting_for_approval(self.run_id, self.execution_key)
        if approval is not None:
            return approval
        approval = AgentApproval(
            run_id=self.run_id,
            capability_id=self.capability_id,
            request_payload={"input": request_input, "proposal_id": self.execution_key,
                             "execution_key": self.execution_key},
        )
        repository.add_approval(approval)
        current = repository.get_run(self.run_id)
        if current is not None and current.status != "waiting_for_approval":
            repository.update_state(self.run_id, expected_revision=current.revision, status="waiting_for_approval")
        return approval

    def settle(self, repository: PostgresAgentRunRepository, *, result_payload: dict[str, Any], error: str | None,
               state_changed: bool = False) -> None:
        """Finish the execution and, when the call holds one, its evidence query with what the result used."""
        repository.finish_capability_execution(
            self.run_id, self.execution_key, result_payload=result_payload, error=error, state_changed=state_changed
        )
        if self.tracks_evidence:
            failed = error is not None
            sources, extracts = evidence_result_usage(result_payload, failed=failed)
            repository.finish_evidence_query(
                self.run_id, cast(str, self.task_revision_id), self.execution_key,
                actual_sources=sources, actual_extracts=extracts, failed=failed,
            )


def evidence_result_usage(result_payload: dict[str, Any], *, failed: bool) -> tuple[int, int]:
    """The sources and extracts a result used; a failed call used none."""
    if failed:
        return 0, 0
    output = result_payload.get("output")
    output = dict(output) if isinstance(output, dict) else {}
    diagnostics = output.get("diagnostics")
    diagnostics = dict(diagnostics) if isinstance(diagnostics, dict) else {}
    items = output.get("items")
    source_count = diagnostics.get("source_count", output.get("source_count"))
    try:
        sources = int(cast(Any, source_count))
    except (TypeError, ValueError):
        sources = len(items) if isinstance(items, list) else 1
    try:
        extracts = int(diagnostics.get("extracted_pages", 0))
    except (TypeError, ValueError):
        extracts = 0
    return max(0, sources), max(0, extracts)


__all__ = ["CapabilityCall", "evidence_result_usage"]
