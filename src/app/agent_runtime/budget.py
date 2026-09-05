"""Durable fail-closed resource budgets for generalized agent runs."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .contracts import AgentRunSnapshot
from .repository import PostgresAgentRunRepository

_ZERO_COST_PROVIDERS = {"lmstudio", "llamacpp", "chatgpt_codex"}
_TERMINAL = {"completed", "failed", "cancelled"}


class AgentBudgetError(RuntimeError):
    pass


def normalize_budget_provider_id(provider_id: str) -> str:
    value = str(provider_id or "").strip().casefold()
    return value.removeprefix("llm:")


class AgentBudgetManager:
    def __init__(
        self,
        database: PostgresDatabase | None = None,
        *,
        context: TenantContext | None = None,
    ) -> None:
        self.database = database or default_database()
        self.context = context or bootstrap_local_tenant(self.database)

    def usage(self, run_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            row = repository.get_usage(run_id)
            work.rollback()
        return row

    def remaining_output_tokens(self, run_id: str) -> int | None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            if snapshot is None:
                raise KeyError(run_id)
            usage = repository.get_usage(run_id)
            maximum = self._effective_limits(repository, snapshot)["max_tokens"]
            work.rollback()
        if maximum is None:
            return None
        return max(0, int(maximum) - int(usage["output_tokens"]))

    def token_metering_required(self, run_id: str) -> bool:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            work.rollback()
        if snapshot is None:
            raise KeyError(run_id)
        return snapshot.spec.limits.max_tokens is not None

    def authorize_model_call(
        self,
        run_id: str,
        *,
        provider_id: str,
    ) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            self._lock_run(repository, run_id)
            snapshot = self._require_runnable(repository, run_id)
            effective = self._effective_limits(repository, snapshot)
            if self._wall_time_exceeded(snapshot):
                reason = "budget_max_wall_time_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            provider = normalize_budget_provider_id(provider_id)
            if (
                snapshot.spec.limits.max_cost is not None
                and provider not in _ZERO_COST_PROVIDERS
            ):
                reason = f"budget_cost_unmeterable_provider:{provider or 'unknown'}"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            current = repository.get_usage(run_id)
            if (
                effective["max_tokens"] is not None
                and int(current["output_tokens"]) >= int(effective["max_tokens"])
            ):
                reason = "budget_output_tokens_exhausted"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            usage = repository.consume_usage(
                run_id,
                steps=1,
                model_calls=1,
                max_steps=int(effective["max_steps"]),
            )
            if usage is None:
                reason = "budget_max_steps_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            work.commit()
            return usage

    def authorize_tool_call(
        self,
        run_id: str,
        *,
        tool_name: str,
    ) -> dict[str, object]:
        del tool_name
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            self._lock_run(repository, run_id)
            snapshot = self._require_runnable(repository, run_id)
            effective = self._effective_limits(repository, snapshot)
            if self._wall_time_exceeded(snapshot):
                reason = "budget_max_wall_time_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            usage = repository.consume_usage(
                run_id,
                tool_calls=1,
                max_tool_calls=int(effective["max_tool_calls"]),
            )
            if usage is None:
                reason = "budget_max_tool_calls_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            work.commit()
            return usage

    def record_output_tokens(self, run_id: str, tokens: int) -> dict[str, object]:
        if tokens < 0:
            raise ValueError("output token usage must be non-negative")
        if tokens == 0:
            return self.usage(run_id)
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            self._lock_run(repository, run_id)
            snapshot = repository.get_run(run_id)
            if snapshot is None:
                raise KeyError(run_id)
            effective = self._effective_limits(repository, snapshot)
            usage = repository.consume_usage(
                run_id,
                output_tokens=tokens,
                max_output_tokens=(
                    int(effective["max_tokens"])
                    if effective["max_tokens"] is not None
                    else None
                ),
            )
            if usage is None:
                reason = "budget_max_output_tokens_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            work.commit()
            return usage

    def enforce_wall_time(self, run_id: str) -> None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            if snapshot is None:
                work.rollback()
                raise KeyError(run_id)
            if snapshot.status in _TERMINAL:
                work.rollback()
                return
            if self._wall_time_exceeded(snapshot):
                reason = "budget_max_wall_time_exceeded"
                self._fail_locked(repository, snapshot, reason)
                work.commit()
                raise AgentBudgetError(reason)
            work.rollback()

    def fail(self, run_id: str, reason: str) -> None:
        with unit_of_work(self.database) as work:
            repository = PostgresAgentRunRepository(work.connection, self.context)
            snapshot = repository.get_run(run_id)
            if snapshot is not None:
                self._fail_locked(repository, snapshot, reason)
            work.commit()

    @staticmethod
    def _lock_run(
        repository: PostgresAgentRunRepository,
        run_id: str,
    ) -> None:
        row = repository.connection.execute(
            """
            SELECT run_id
              FROM omnix_agent_runs
             WHERE workspace_id = %s AND run_id = %s
             FOR UPDATE
            """,
            (repository.context.workspace_id, run_id),
        ).fetchone()
        if row is None:
            raise KeyError(run_id)

    @staticmethod
    def _quality_reserve(snapshot: AgentRunSnapshot, children: list[AgentRunSnapshot]) -> dict[str, int | float]:
        spec = snapshot.spec
        if (
            spec.profile != "coding"
            or "diff" not in spec.expected_artifacts
            or spec.quality_policy == "off"
            or any(child.spec.profile == "coding-reviewer" for child in children)
        ):
            return {"steps": 0, "tools": 0, "tokens": 0, "cost": 0.0}
        fraction = max(0.0, min(float(spec.quality_reserve_fraction), 0.5))
        return {
            "steps": max(1, int(spec.limits.max_steps * fraction)) if fraction else 0,
            "tools": max(1, int(spec.limits.max_tool_calls * fraction)) if fraction else 0,
            "tokens": max(1, int(spec.limits.max_tokens * fraction)) if fraction and spec.limits.max_tokens is not None else 0,
            "cost": spec.limits.max_cost * fraction if fraction and spec.limits.max_cost is not None else 0.0,
        }

    @classmethod
    def _effective_limits(
        cls,
        repository: PostgresAgentRunRepository,
        snapshot: AgentRunSnapshot,
    ) -> dict[str, int | float | None]:
        children = repository.list_children(snapshot.run_id)
        limits = snapshot.spec.limits
        reserved_steps = sum(child.spec.limits.max_steps for child in children)
        reserved_tools = sum(child.spec.limits.max_tool_calls for child in children)
        reserved_tokens = sum(child.spec.limits.max_tokens or 0 for child in children)
        reserved_cost = sum(child.spec.limits.max_cost or 0.0 for child in children)
        quality = cls._quality_reserve(snapshot, children)
        return {
            "max_steps": max(0, limits.max_steps - reserved_steps - int(quality["steps"])),
            "max_tool_calls": max(0, limits.max_tool_calls - reserved_tools - int(quality["tools"])),
            "max_tokens": (
                max(0, limits.max_tokens - reserved_tokens - int(quality["tokens"]))
                if limits.max_tokens is not None
                else None
            ),
            "max_cost": (
                max(0.0, limits.max_cost - reserved_cost - float(quality["cost"]))
                if limits.max_cost is not None
                else None
            ),
        }

    @staticmethod
    def _require_runnable(
        repository: PostgresAgentRunRepository,
        run_id: str,
    ) -> AgentRunSnapshot:
        snapshot = repository.get_run(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        if snapshot.status in _TERMINAL or snapshot.desired_state != "running":
            raise AgentBudgetError(f"agent_run_not_runnable:{snapshot.status}")
        return snapshot

    @staticmethod
    def _wall_time_exceeded(snapshot: AgentRunSnapshot) -> bool:
        anchor = snapshot.started_at or snapshot.created_at
        elapsed = max(
            0.0,
            (datetime.now(timezone.utc) - anchor).total_seconds(),
        )
        return elapsed > snapshot.spec.limits.max_wall_time_seconds

    @staticmethod
    def _fail_locked(
        repository: PostgresAgentRunRepository,
        snapshot: AgentRunSnapshot,
        reason: str,
    ) -> None:
        if snapshot.status in _TERMINAL:
            return
        current = repository.get_run(snapshot.run_id) or snapshot
        if current.status in _TERMINAL:
            return
        repository.update_state(
            snapshot.run_id,
            expected_revision=current.revision,
            status="failed",
            desired_state="cancelled",
            last_error=reason[:2000],
        )


@lru_cache(maxsize=1)
def default_agent_budget_manager() -> AgentBudgetManager:
    return AgentBudgetManager()
