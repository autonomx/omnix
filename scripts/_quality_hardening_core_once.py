from __future__ import annotations

from pathlib import Path
import re

ROOT = Path.cwd()


def f(name: str) -> Path:
    return ROOT / name


def rep(name: str, old: str, new: str, count: int = 1) -> None:
    p = f(name)
    text = p.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{name}: expected {count} matches, found {actual}: {old[:100]!r}")
    p.write_text(text.replace(old, new), encoding="utf-8")


def rx(name: str, pattern: str, new: str) -> None:
    p = f(name)
    text = p.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, new, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{name}: regex expected 1 match, found {count}")
    p.write_text(updated, encoding="utf-8")


# Phase 20: preserve selected provider reasoning before RunSpec persistence.
rx(
    "src/app/agent_runtime/chat_bridge.py",
    r"def _agent_reasoning_effort\(\) -> str:\n.*?\n    return configured\n",
    '''def _agent_reasoning_effort(provider_id: str | None = None) -> str:
    """Return the selected reasoning level for Chat-created Pi runs."""
    configured = os.environ.get("OMNIX_AGENT_REASONING_EFFORT", "").strip()
    if configured:
        return _DEFAULT_AGENT_REASONING_EFFORT if configured.casefold() in {"off", "disabled"} else configured
    provider_key = str(provider_id or "").strip().removeprefix("llm:")
    if provider_key:
        try:
            from app import shared
            provider = shared.get_provider(provider_key)
            value = str(getattr(provider, "reasoning_effort", "") or "").strip()
            if not value:
                config = getattr(provider, "config", None)
                extra = getattr(config, "extra_params", None)
                if isinstance(extra, dict):
                    value = str(extra.get("reasoning_effort") or "").strip()
            if value:
                return value
        except Exception:
            pass
    return _DEFAULT_AGENT_REASONING_EFFORT
''',
)
rep(
    "src/app/agent_runtime/chat_bridge.py",
    "reasoning_effort=_agent_reasoning_effort(),",
    "reasoning_effort=_agent_reasoning_effort(resolved_provider),",
    2,
)
rep(
    "src/app/agent_runtime/model_fidelity.py",
    '            "requested_reasoning_effort": requested or None,\n',
    '            "requested_provider_id": model.provider_id,\n'
    '            "resolved_provider_id": model.provider_id,\n'
    '            "requested_model_id": model.model_id,\n'
    '            "resolved_model_id": model.model_id,\n'
    '            "requested_reasoning_effort": requested or None,\n',
)

# Phase 22/24 contracts.
rep(
    "src/app/agent_runtime/contracts.py",
    "    output_digest: str\n    started_at: datetime | None = None\n",
    "    output_digest: str\n    covers_requirement_ids: list[str] = Field(default_factory=list)\n    started_at: datetime | None = None\n",
)
rep(
    "src/app/agent_runtime/contracts.py",
    "class ReviewSnapshot(BaseModel):\n",
    '''class SelfReviewResult(BaseModel):
    """Structured implementer self-review bound to one exact final state."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    self_review_result_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    task_revision_id: str | None = None
    workspace_state_id: str
    verdict: ReviewVerdict
    requirements: list[ReviewRequirementResult] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    missing_tests: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ReviewSnapshot(BaseModel):
''',
)

# Validation identity, structured self-review, and review snapshot integrity.
rep("src/app/agent_runtime/coding_quality.py", "    ReviewSnapshot,\n", "    ReviewSnapshot,\n    SelfReviewResult,\n")
rep(
    "src/app/agent_runtime/coding_quality.py",
    "    return ValidationResult(\n        result_id=result_id,\n        run_id=run_id,\n        validation_id=validation_id_for_kind(kind, revision),\n        kind=kind,\n",
    '''    validation_id = validation_id_for_kind(kind, revision)
    validation_spec = next((item for item in (revision.validation_plan if revision is not None else []) if item.id == validation_id), None)
    covers_requirement_ids = list(validation_spec.covers) if validation_spec is not None else []
    return ValidationResult(
        result_id=result_id,
        run_id=run_id,
        validation_id=validation_id,
        kind=kind,
''',
)
rep(
    "src/app/agent_runtime/coding_quality.py",
    "        output_digest=output_digest,\n        finished_at=event.created_at,\n",
    "        output_digest=output_digest,\n        covers_requirement_ids=covers_requirement_ids,\n        finished_at=event.created_at,\n",
)
rep(
    "src/app/agent_runtime/coding_quality.py",
    "        if not any(\n            observed.validation_id == expected.id or observed.kind == expected.kind\n            for observed in current\n        ):\n",
    '''        expected_coverage = set(expected.covers)
        if not any(
            observed.validation_id == expected.id
            and expected_coverage.issubset(set(observed.covers_requirement_ids))
            for observed in current
        ):
''',
)
rep(
    "src/app/agent_runtime/coding_quality.py",
    "def materialize_review_workspace(\n",
    '''def _workspace_matches_state(spec: AgentRunSpec, state: WorkspaceState, workspace: WorkspaceSpec) -> bool:
    observed = capture_workspace_state(spec.model_copy(update={"workspace": workspace}), task_revision_id=state.task_revision_id)
    return bool(observed is not None and observed.state_id == state.state_id and observed.base_commit_sha == state.base_commit_sha)


def review_workspace_matches_snapshot(spec: AgentRunSpec, snapshot: ReviewSnapshot) -> bool:
    parent = spec.workspace
    if parent is None:
        return False
    workspace = WorkspaceSpec(
        root=snapshot.workspace_root,
        repository=parent.repository or parent.root,
        base_ref=snapshot.base_commit_sha,
        worktree=snapshot.workspace_root,
        isolation_policy="immutable_review_snapshot",
        allowed_paths=list(parent.allowed_paths),
        forbidden_paths=list(parent.forbidden_paths),
    )
    expected = WorkspaceState(
        state_id=snapshot.workspace_state_id,
        run_id=spec.run_id,
        task_revision_id=snapshot.task_revision_id,
        base_commit_sha=snapshot.base_commit_sha,
        tracked_diff_sha256="",
        untracked_file_manifest_sha256="",
    )
    return _workspace_matches_state(spec, expected, workspace)


def materialize_review_workspace(
''',
)
rep(
    "src/app/agent_runtime/coding_quality.py",
    '''    if target.exists():
        return WorkspaceSpec(
            root=str(target),
            repository=str(repository),
            base_ref=state.base_commit_sha,
            worktree=str(target),
            isolation_policy="immutable_review_snapshot",
            allowed_paths=list(workspace.allowed_paths),
            forbidden_paths=list(workspace.forbidden_paths),
        )
''',
    '''    if target.exists():
        review_workspace = WorkspaceSpec(
            root=str(target), repository=str(repository), base_ref=state.base_commit_sha,
            worktree=str(target), isolation_policy="immutable_review_snapshot",
            allowed_paths=list(workspace.allowed_paths), forbidden_paths=list(workspace.forbidden_paths),
        )
        if _workspace_matches_state(spec, state, review_workspace):
            return review_workspace
        raise WorkspacePolicyError("existing review snapshot no longer reproduces the bound WorkspaceState")
''',
)
rep(
    "src/app/agent_runtime/coding_quality.py",
    "def review_prompt(\n",
    '''def parse_self_review_result(text: str, *, run_id: str, revision: TaskRevision, workspace_state_id: str) -> SelfReviewResult:
    match = _JSON_OBJECT.search(str(text or "").strip())
    payload: dict[str, object] = {}
    if match is not None:
        try:
            decoded = json.loads(match.group(0))
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            pass
    verdict = str(payload.get("verdict") or "blocked")
    if verdict not in {"approve", "changes_required", "blocked"}:
        verdict = "blocked"
    requirements: list[ReviewRequirementResult] = []
    for row in payload.get("requirements") or []:
        if isinstance(row, dict):
            try: requirements.append(ReviewRequirementResult.model_validate(row))
            except Exception: pass
    findings: list[ReviewFinding] = []
    for row in payload.get("findings") or []:
        if isinstance(row, dict):
            try: findings.append(ReviewFinding.model_validate(row))
            except Exception: pass
    if not payload:
        findings.append(ReviewFinding(severity="high", category="self_review_protocol", problem="Implementer did not return the required structured self-review JSON.", recommended_fix="Repeat the mandatory self-review against the same final state."))
    return SelfReviewResult(
        run_id=run_id, task_revision_id=revision.revision_id, workspace_state_id=workspace_state_id,
        verdict=verdict, requirements=requirements, findings=findings,
        missing_tests=[str(item) for item in payload.get("missing_tests") or [] if str(item).strip()],
        residual_risks=[str(item) for item in payload.get("residual_risks") or [] if str(item).strip()],
    )


def self_review_is_acceptable(result: SelfReviewResult, revision: TaskRevision) -> bool:
    if result.verdict != "approve": return False
    required_ids = {item.id for item in revision.requirements if item.required}
    statuses = {item.requirement_id: item.status for item in result.requirements}
    if required_ids and any(statuses.get(item) != "satisfied" for item in required_ids): return False
    if any(item.severity in {"blocker", "high"} for item in result.findings): return False
    return not result.missing_tests


def review_prompt(
''',
)
rep("src/app/agent_runtime/coding_quality.py", "    events: Iterable[AgentEvent],\n) -> list[str]:\n", "    self_reviews: Iterable[SelfReviewResult],\n) -> list[str]:\n")
rep(
    "src/app/agent_runtime/coding_quality.py",
    '''    self_review_ok = any(
        event.event_type == "quality.self_review_completed"
        and event.payload.get("workspace_state_id") == workspace_state.state_id
        and event.payload.get("task_revision_id") == revision_id
        for event in events
    )
''',
    '''    self_review_ok = any(
        item.workspace_state_id == workspace_state.state_id
        and item.task_revision_id == revision_id
        and revision is not None
        and self_review_is_acceptable(item, revision)
        for item in self_reviews
    )
''',
)
rep("src/app/agent_runtime/coding_quality.py", "    review: ReviewResult | None,\n", "    review: ReviewResult | SelfReviewResult | None,\n")
rx(
    "src/app/agent_runtime/coding_quality.py",
    r"def self_review_prompt\(revision: TaskRevision, \*, attempt: int\) -> str:\n.*?\n\n\ndef validation_prompt",
    '''def self_review_prompt(revision: TaskRevision, *, attempt: int) -> str:
    requirements = [item.model_dump(mode="json") for item in revision.requirements]
    return (
        f"Mandatory engineering self-review for quality attempt {attempt}. Do not declare completion yet.\\n"
        f"Authoritative requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\\n"
        "Inspect the complete current diff, callers, interfaces, generated contracts, edge cases and regression coverage. Fix material issues before returning. Rerun required validation after the final mutation.\\n"
        "Return ONLY JSON: {\\\"verdict\\\":\\\"approve|changes_required|blocked\\\",\\\"requirements\\\":[{\\\"requirement_id\\\":\\\"R\\\",\\\"status\\\":\\\"satisfied|partial|missing|not_applicable\\\",\\\"evidence\\\":\\\"...\\\"}],\\\"findings\\\":[{\\\"severity\\\":\\\"blocker|high|medium|low\\\",\\\"category\\\":\\\"correctness\\\",\\\"file\\\":null,\\\"location\\\":null,\\\"problem\\\":\\\"...\\\",\\\"recommended_fix\\\":null}],\\\"missing_tests\\\":[],\\\"residual_risks\\\":[]}."
    )


def validation_prompt''',
)

# Durable evidence repository.
rep("src/app/agent_runtime/coding_quality_repository.py", "from .contracts import ReviewResult, ReviewSnapshot, ValidationResult, WorkspaceState\n", "from .contracts import ReviewResult, ReviewSnapshot, SelfReviewResult, ValidationResult, WorkspaceState\n")
rep(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                task_revision_id, workspace_state_id, command, exit_code,
                success, output_digest, started_at, finished_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
''',
    '''                task_revision_id, workspace_state_id, command, exit_code,
                success, output_digest, covers_requirement_ids, started_at, finished_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
''',
)
rep("src/app/agent_runtime/coding_quality_repository.py", "                result.output_digest,\n                result.started_at,\n", "                result.output_digest,\n                _json(result.covers_requirement_ids),\n                result.started_at,\n")
rep(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                       workspace_state_id, command, exit_code, success,
                       output_digest, started_at, finished_at, metadata
''',
    '''                       workspace_state_id, command, exit_code, success,
                       output_digest, covers_requirement_ids, started_at, finished_at, metadata
''',
    2,
)
rep(
    "src/app/agent_runtime/coding_quality_repository.py",
    '''                output_digest=str(row[8]),
                started_at=row[9],
                finished_at=row[10],
                metadata=dict(row[11] or {}),
''',
    '''                output_digest=str(row[8]),
                covers_requirement_ids=list(row[9] or []),
                started_at=row[10], finished_at=row[11], metadata=dict(row[12] or {}),
''',
)
rep(
    "src/app/agent_runtime/coding_quality_repository.py",
    "    def add_review_snapshot(self, snapshot: ReviewSnapshot) -> ReviewSnapshot:\n",
    '''    def add_self_review_result(self, result: SelfReviewResult) -> SelfReviewResult:
        self.connection.execute("""
            INSERT INTO omnix_agent_self_review_results (
                workspace_id, run_id, self_review_result_id, task_revision_id, workspace_state_id,
                verdict, requirements, findings, missing_tests, residual_risks, created_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s)
            ON CONFLICT (workspace_id, run_id, self_review_result_id) DO NOTHING
        """, (self.context.workspace_id, result.run_id, result.self_review_result_id, result.task_revision_id,
              result.workspace_state_id, result.verdict, _json(result.requirements), _json(result.findings),
              _json(result.missing_tests), _json(result.residual_risks), result.created_at))
        return result

    def list_self_review_results(self, run_id: str, *, task_revision_id: str | None = None) -> list[SelfReviewResult]:
        where = "WHERE workspace_id = %s AND run_id = %s"
        args: tuple[object, ...] = (self.context.workspace_id, run_id)
        if task_revision_id is not None:
            where += " AND task_revision_id = %s"
            args = (*args, task_revision_id)
        rows = self.connection.execute(f"""
            SELECT self_review_result_id, task_revision_id, workspace_state_id, verdict,
                   requirements, findings, missing_tests, residual_risks, created_at
              FROM omnix_agent_self_review_results {where}
             ORDER BY created_at, self_review_result_id
        """, args).fetchall()
        return [SelfReviewResult(self_review_result_id=str(row[0]), run_id=run_id,
            task_revision_id=str(row[1]) if row[1] else None, workspace_state_id=str(row[2]), verdict=str(row[3]),
            requirements=list(row[4] or []), findings=list(row[5] or []), missing_tests=list(row[6] or []),
            residual_risks=list(row[7] or []), created_at=row[8]) for row in rows]

    def add_review_snapshot(self, snapshot: ReviewSnapshot) -> ReviewSnapshot:
''',
)

# Forward migration so already-applied 0061 installations still upgrade.
f("src/app/persistence/migrations/0062_agent_coding_quality_hardening.sql").write_text('''-- Final coding-quality hardening.
ALTER TABLE omnix_agent_validation_results
    ADD COLUMN IF NOT EXISTS covers_requirement_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE TABLE IF NOT EXISTS omnix_agent_self_review_results (
    workspace_id TEXT NOT NULL, run_id TEXT NOT NULL, self_review_result_id TEXT NOT NULL,
    task_revision_id TEXT, workspace_state_id TEXT NOT NULL, verdict TEXT NOT NULL,
    requirements JSONB NOT NULL DEFAULT '[]'::jsonb, findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_tests JSONB NOT NULL DEFAULT '[]'::jsonb, residual_risks JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workspace_id, run_id, self_review_result_id),
    FOREIGN KEY (workspace_id, run_id) REFERENCES omnix_agent_runs(workspace_id, run_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, run_id, workspace_state_id) REFERENCES omnix_agent_workspace_states(workspace_id, run_id, state_id) ON DELETE CASCADE,
    CHECK (verdict IN ('approve','changes_required','blocked'))
);
CREATE INDEX IF NOT EXISTS idx_omnix_agent_self_review_state ON omnix_agent_self_review_results
    (workspace_id, run_id, task_revision_id, workspace_state_id, verdict, created_at DESC);
''', encoding="utf-8")

# Service controller hardening.
rep("src/app/agent_runtime/service.py", "    parse_review_result,\n", "    parse_review_result,\n    parse_self_review_result,\n")
rep("src/app/agent_runtime/service.py", "    review_prompt,\n    self_review_prompt,\n", "    review_prompt,\n    review_workspace_matches_snapshot,\n    self_review_is_acceptable,\n    self_review_prompt,\n")
rep("src/app/agent_runtime/service.py", "    ReviewSnapshot,\n    TaskRevision,\n", "    ReviewSnapshot,\n    SelfReviewResult,\n    TaskRevision,\n")
rep("src/app/agent_runtime/service.py", 'stage="implementing",', 'stage="inspect",', 2)
rep("src/app/agent_runtime/service.py", '"stage": "implementing",', '"stage": "inspect",', 2)
rep("src/app/agent_runtime/service.py", "    def review_results(self, run_id: str):\n", '''    def self_review_results(self, run_id: str):
        with unit_of_work(self.database) as work:
            rows = PostgresCodingQualityRepository(work.connection, self.context).list_self_review_results(run_id)
            work.rollback()
        return rows

    def review_results(self, run_id: str):
''')
rep(
    "src/app/agent_runtime/service.py",
    '''            command = str(args.get("command") or "")
            mutating_or_validation = tool in {"edit", "write", "bash", "powershell"} or validation_kind_for_command(command) is not None
            if not mutating_or_validation:
                work.rollback()
                return
            revision = self._current_revision(repository, event.run_id)
''',
    '''            command = str(args.get("command") or "")
            quality = PostgresCodingQualityRepository(work.connection, self.context)
            stage_state = quality.get_stage(event.run_id) or {}
            stage_now = str(stage_state.get("stage") or "")
            attempt = max(1, int(stage_state.get("attempt") or 1))
            revision_key = stage_state.get("task_revision_id")
            if stage_now == "inspect" and tool in {"read", "ls", "grep"}:
                self._set_quality_stage(repository, run_id=event.run_id, stage="planning", attempt=attempt,
                    task_revision_id=str(revision_key) if revision_key else None, reason="repository_inspection_observed")
                stage_now = "planning"
            if stage_now in {"inspect", "planning"} and tool in {"edit", "write"}:
                self._set_quality_stage(repository, run_id=event.run_id, stage="implementing", attempt=attempt,
                    task_revision_id=str(revision_key) if revision_key else None, reason="first_workspace_mutation_observed")
            mutating_or_validation = tool in {"edit", "write", "bash", "powershell"} or validation_kind_for_command(command) is not None
            if not mutating_or_validation:
                work.commit()
                return
            revision = self._current_revision(repository, event.run_id)
''',
)
rep("src/app/agent_runtime/service.py", "            quality = PostgresCodingQualityRepository(repository.connection, self.context)\n            quality.add_workspace_state(state)\n", "            quality.add_workspace_state(state)\n")
rep(
    "src/app/agent_runtime/service.py",
    '''        if stage == "self_review":
            repository.append_event(
                AgentEvent(
                    run_id=current.run_id,
                    event_type="quality.self_review_completed",
                    payload={
                        "attempt": attempt,
                        "task_revision_id": revision.revision_id,
                        "workspace_state_id": state.state_id,
                    },
                )
            )
            self._set_quality_stage(
                repository,
                run_id=current.run_id,
                stage="validating",
                attempt=attempt,
                task_revision_id=revision.revision_id,
                workspace_state_id=state.state_id,
            )

        events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
        self_review_fresh = any(
            item.event_type == "quality.self_review_completed"
            and item.payload.get("task_revision_id") == revision.revision_id
            and item.payload.get("workspace_state_id") == state.state_id
            for item in events
        )
        if not self_review_fresh:
''',
    '''        if stage == "self_review":
            events = repository.list_events(current.run_id, after_sequence=0, limit=5000)
            text = next((str(item.payload.get("text") or "").strip() for item in reversed(events)
                         if item.event_type == "model.message" and str(item.payload.get("text") or "").strip()), "")
            self_review = parse_self_review_result(text, run_id=current.run_id, revision=revision, workspace_state_id=state.state_id)
            quality.add_self_review_result(self_review)
            repository.append_event(AgentEvent(run_id=current.run_id, event_type="quality.self_review_completed", payload={
                "attempt": attempt, "self_review_result_id": self_review.self_review_result_id, "verdict": self_review.verdict,
                "requirements": [item.model_dump(mode="json") for item in self_review.requirements],
                "findings": [item.model_dump(mode="json") for item in self_review.findings],
                "missing_tests": list(self_review.missing_tests), "residual_risks": list(self_review.residual_risks),
                "task_revision_id": revision.revision_id, "workspace_state_id": state.state_id,
            }))
            if not self_review_is_acceptable(self_review, revision):
                self._request_quality_repair(repository, current, revision, self_review, failures=["quality_self_review_not_approved"])
                return None
            self._set_quality_stage(repository, run_id=current.run_id, stage="validating", attempt=attempt,
                task_revision_id=revision.revision_id, workspace_state_id=state.state_id)

        self_reviews = quality.list_self_review_results(current.run_id, task_revision_id=revision.revision_id)
        self_review_fresh = any(item.workspace_state_id == state.state_id and self_review_is_acceptable(item, revision) for item in self_reviews)
        if not self_review_fresh:
''',
)
rep(
    "src/app/agent_runtime/service.py",
    "                per_reviewer_fraction = parent.spec.quality_reserve_fraction / max(1, count)\n",
    '''                if not review_workspace_matches_snapshot(parent.spec, snapshot):
                    latest = repository.get_run(parent_run_id) or parent
                    repository.update_state(parent_run_id, expected_revision=latest.revision, status="failed",
                        desired_state="cancelled", last_error="quality_review_snapshot_integrity_mismatch")
                    work.commit()
                    return
                per_reviewer_fraction = parent.spec.quality_reserve_fraction / max(1, count * quality_attempt_limit())
''',
)
rep("src/app/agent_runtime/service.py", "        review: ReviewResult | None,\n", "        review: ReviewResult | SelfReviewResult | None,\n")
rep(
    "src/app/agent_runtime/service.py",
    '''        reviews = quality.list_review_results(current.run_id, task_revision_id=revision_id)
        quality_failures = quality_failure_reasons(
            current,
            revision,
            state,
            validations,
            reviews,
            all_events,
        )
''',
    '''        reviews = quality.list_review_results(current.run_id, task_revision_id=revision_id)
        self_reviews = quality.list_self_review_results(current.run_id, task_revision_id=revision_id)
        quality_failures = quality_failure_reasons(current, revision, state, validations, reviews, self_reviews)
''',
)

# 65/25/10 budget envelope; review budget is shared across attempts.
rx(
    "src/app/agent_runtime/budget.py",
    r"    @staticmethod\n    def _quality_reserve\(snapshot: AgentRunSnapshot, children: list\[AgentRunSnapshot\]\) -> dict\[str, int \| float\]:\n.*?\n    @classmethod\n    def _effective_limits",
    '''    @staticmethod
    def _quality_state(repository: PostgresAgentRunRepository, snapshot: AgentRunSnapshot) -> tuple[str | None, int]:
        try:
            row = repository.connection.execute("SELECT stage, attempt FROM omnix_agent_coding_quality_state WHERE workspace_id = %s AND run_id = %s", (repository.context.workspace_id, snapshot.run_id)).fetchone()
        except Exception:
            return None, 1
        return (str(row[0]), max(1, int(row[1] or 1))) if row else (None, 1)

    @classmethod
    def _quality_reserve(cls, repository: PostgresAgentRunRepository, snapshot: AgentRunSnapshot, children: list[AgentRunSnapshot]) -> dict[str, int | float]:
        spec = snapshot.spec
        if spec.profile != "coding" or "diff" not in spec.expected_artifacts or spec.quality_policy == "off":
            return {"steps": 0, "tools": 0, "tokens": 0, "cost": 0.0}
        review_fraction = max(0.0, min(float(spec.quality_reserve_fraction), 0.5))
        stage, attempt = cls._quality_state(repository, snapshot)
        repair_fraction = 0.10 if attempt <= 1 and stage != "repairing" else 0.0
        reviewers = [child for child in children if child.spec.profile == "coding-reviewer"]
        def rem(maximum, attr, fraction):
            if maximum is None or not fraction: return 0
            target = max(1, int(maximum * fraction))
            used = sum(int(getattr(child.spec.limits, attr) or 0) for child in reviewers)
            return max(0, target - used)
        def rem_cost(maximum, fraction):
            if maximum is None or not fraction: return 0.0
            return max(0.0, float(maximum) * fraction - sum(float(child.spec.limits.max_cost or 0.0) for child in reviewers))
        return {
            "steps": rem(spec.limits.max_steps, "max_steps", review_fraction) + (max(1, int(spec.limits.max_steps * repair_fraction)) if repair_fraction else 0),
            "tools": rem(spec.limits.max_tool_calls, "max_tool_calls", review_fraction) + (max(1, int(spec.limits.max_tool_calls * repair_fraction)) if repair_fraction else 0),
            "tokens": rem(spec.limits.max_tokens, "max_tokens", review_fraction) + (max(1, int(spec.limits.max_tokens * repair_fraction)) if repair_fraction and spec.limits.max_tokens is not None else 0),
            "cost": rem_cost(spec.limits.max_cost, review_fraction) + (float(spec.limits.max_cost) * repair_fraction if repair_fraction and spec.limits.max_cost is not None else 0.0),
        }

    @classmethod
    def _effective_limits''',
)
rep("src/app/agent_runtime/budget.py", "        quality = cls._quality_reserve(snapshot, children)\n", "        quality = cls._quality_reserve(repository, snapshot, children)\n")
rx(
    "src/app/agent_runtime/subagents.py",
    r"def default_reviewer_limits\(parent: RunLimits, reserve_fraction: float = 0\.25\) -> RunLimits:\n.*?\n\n\ndef _default_child_limits",
    '''def default_reviewer_limits(parent: RunLimits, reserve_fraction: float = 0.25) -> RunLimits:
    fraction = max(0.01, min(float(reserve_fraction), 0.5))
    return RunLimits(
        max_steps=max(1, min(60, int(parent.max_steps * fraction) or 1)),
        max_wall_time_seconds=max(1, min(parent.max_wall_time_seconds, 1200, max(30, int(parent.max_wall_time_seconds * fraction) or 1))),
        max_tokens=max(1, int(parent.max_tokens * fraction)) if parent.max_tokens is not None else None,
        max_cost=parent.max_cost * fraction if parent.max_cost is not None else None,
        max_tool_calls=max(1, min(120, int(parent.max_tool_calls * fraction) or 1)),
    )


def _default_child_limits''',
)

# Hidden API + Codex-style visible stages.
rep("src/app/agent_runtime/api.py", "    ReviewResult,\n", "    ReviewResult,\n    SelfReviewResult,\n")
rep(
    "src/app/agent_runtime/api.py",
    '@router.get("/{run_id}/quality/reviews", response_model=list[ReviewResult], include_in_schema=False)\n',
    '''@router.get("/{run_id}/quality/self-reviews", response_model=list[SelfReviewResult], include_in_schema=False)
def list_agent_self_review_results(run_id: str) -> list[SelfReviewResult]:
    if _service().get(run_id) is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    return _service().self_review_results(run_id)


@router.get("/{run_id}/quality/reviews", response_model=list[ReviewResult], include_in_schema=False)
''',
)
rep(
    "src/apps/web/src/features/chatbot/OmnixRunCard.tsx",
    "const QUALITY_STAGES: Array<{ id: QualityStage; label: string }> = [\n  { id: 'implementing', label: 'Implement' },\n",
    "const QUALITY_STAGES: Array<{ id: QualityStage; label: string }> = [\n  { id: 'inspect', label: 'Inspect' },\n  { id: 'planning', label: 'Plan' },\n  { id: 'implementing', label: 'Implement' },\n",
)

print("core hardening applied")
