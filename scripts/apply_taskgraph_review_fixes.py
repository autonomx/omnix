from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one replacement target, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_region(relative: str, start: str, end: str, transform) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    region = text[start_index:end_index]
    updated = transform(region)
    if updated == region:
        return
    path.write_text(text[:start_index] + updated + text[end_index:], encoding="utf-8")


def append_once(relative: str, marker: str, addition: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return
    path.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n", encoding="utf-8")


# P1: approval policy must never widen the capability set issued to a Pi run.
replace_once(
    "src/app/agent_runtime/pi_guard_extension.ts",
    '''      const commandNeedsApproval = approvalPolicy !== "allow_automatic"
        && (approvalPolicy === "always_ask" || !commandPrefixAllowed(input.command));
      if (commandNeedsApproval) {
        if (localCapabilities.has("workspace.command")) {
          const permissionRejection = await authorizeBlockedCommand(input.command as string, input.cwd);
          if (permissionRejection) return { block: true, reason: permissionRejection };
        } else {
          const rejection = commandRejectionReason(input.command);
          if (rejection) return { block: true, reason: rejection };
        }
      }
''',
    '''      const commandAllowedByIssuedCapability = commandPrefixAllowed(input.command);
      if (!commandAllowedByIssuedCapability && !localCapabilities.has("workspace.command")) {
        const rejection = commandRejectionReason(input.command);
        if (rejection) return { block: true, reason: rejection };
      }
      const commandNeedsApproval = localCapabilities.has("workspace.command")
        && approvalPolicy !== "allow_automatic"
        && (approvalPolicy === "always_ask" || !commandAllowedByIssuedCapability);
      if (commandNeedsApproval) {
        const permissionRejection = await authorizeBlockedCommand(input.command as string, input.cwd);
        if (permissionRejection) return { block: true, reason: permissionRejection };
      }
''',
)

# P1/P2: only provider-returned web items can prove coverage, and source counts
# are attributed to the individual coverage identity they actually support.
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''def _coverage_token_observed(token: str, output: dict[str, object]) -> bool:
    normalized_token = _normalized_coverage_text(token)
    if not normalized_token:
        return False
    observed = _normalized_coverage_text(
        json.dumps(output, sort_keys=True, default=str)
    )
    if not observed:
        return False
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_token)}(?![a-z0-9])",
            observed,
        )
    )
''',
    '''def _web_source_items(output: dict[str, object]) -> list[dict[str, object]]:
    """Return only provider-returned source records that can carry evidence.

    Request echoes, diagnostics, query text and other envelope metadata are
    intentionally excluded so the search request cannot prove its own subject.
    """

    items = output.get("items")
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, dict)]


def _coverage_token_observed(token: str, output: dict[str, object]) -> bool:
    normalized_token = _normalized_coverage_text(token)
    if not normalized_token:
        return False
    items = _web_source_items(output)
    observed = _normalized_coverage_text(
        json.dumps(items, sort_keys=True, default=str)
    )
    if not observed:
        return False
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_token)}(?![a-z0-9])",
            observed,
        )
    )
''',
)

replace_once(
    "src/app/agent_runtime/evidence.py",
    '''def evaluate_evidence_set(
    run_id: str,
''',
    '''def _receipt_source_units_for_requirement(
    requirement: EvidenceRequirement,
    receipt: EvidenceReceipt,
) -> int:
    """Count source units for the exact subject/coverage being evaluated."""

    if requirement.coverage is not None:
        coverage_key = evidence_coverage_key(requirement.coverage)
        counts = receipt.metadata.get("evidence_source_counts_by_coverage")
        if isinstance(counts, dict) and coverage_key in counts:
            try:
                return max(0, int(counts[coverage_key]))
            except (TypeError, ValueError):
                return 0
    # Receipts created before per-coverage accounting remain compatible. A
    # newly built multi-coverage web receipt always carries the map above.
    return max(1, int(receipt.source_count or 0))


def evaluate_evidence_set(
    run_id: str,
''',
)
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''            matched.append(receipt.receipt_id)
            matched_units += max(1, int(receipt.source_count or 0))
            accepted_receipts.add(receipt.receipt_id)
''',
    '''            matched.append(receipt.receipt_id)
            matched_units += _receipt_source_units_for_requirement(requirement, receipt)
            accepted_receipts.add(receipt.receipt_id)
''',
)
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''    return rows


def build_evidence_receipt(
''',
    '''    return rows


def _coverage_source_counts(
    coverages: list[EvidenceCoverage],
    output: dict[str, object],
) -> dict[str, int]:
    """Count returned web source records separately for every coverage key."""

    items = _web_source_items(output)
    if not items:
        return {}
    counts: dict[str, int] = {}
    for coverage in coverages:
        coverage_key = evidence_coverage_key(coverage)
        if coverage_key == "unbound":
            continue
        count = 0
        for item in items:
            item_output: dict[str, object] = {"items": [item]}
            if coverage.subject is not None:
                supported = _subject_supported_by_web_output(coverage.subject, item_output)
            else:
                supported = _coverage_supported_by_observation(
                    coverage,
                    subject=None,
                    output=item_output,
                )
            if supported:
                count += 1
        counts[coverage_key] = count
    return counts


def build_evidence_receipt(
''',
)
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''    observed_coverage = _compatible_observed_coverages(
        policy,
        capability_id=capability_id,
        source_class=source_class,
        subject=subject,
        output=output,
    )
    return EvidenceReceipt(
''',
    '''    observed_coverage = _compatible_observed_coverages(
        policy,
        capability_id=capability_id,
        source_class=source_class,
        subject=subject,
        output=output,
    )
    coverage_source_counts = (
        _coverage_source_counts(observed_coverage, output)
        if capability_id == "research.web_search"
        else {}
    )
    return EvidenceReceipt(
''',
)
replace_once(
    "src/app/agent_runtime/evidence.py",
    '''            "evidence_source_class": source_class,
            "evidence_coverage_count": len(observed_coverage),
''',
    '''            "evidence_source_class": source_class,
            "evidence_coverage_count": len(observed_coverage),
            "evidence_source_counts_by_coverage": coverage_source_counts,
''',
)

append_once(
    "src/tests/agent_runtime/test_evidence_coverage.py",
    "test_web_receipt_does_not_treat_echoed_query_as_returned_evidence",
    r'''
def test_web_receipt_does_not_treat_echoed_query_as_returned_evidence() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            _requirement("react", "React"),
            _requirement("vue", "Vue"),
        ],
    )

    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "React Vue stable releases"},
        result_payload={
            "output": {
                "query": "React Vue stable releases",
                "items": [
                    {
                        "url": "https://github.com/example/svelte",
                        "title": "Svelte stable release",
                        "snippet": "Svelte shipped a stable release.",
                    }
                ],
            }
        },
        error=None,
        requirement_id="react",
        source_class_hint="software_release",
    )

    assert receipt is not None
    assert receipt.coverage == []


def test_batched_web_source_counts_are_scoped_per_coverage_subject() -> None:
    policy = EvidencePolicy(
        requirement="required",
        requirements=[
            _requirement("react", "React").model_copy(update={"minimum_matches": 2}),
            _requirement("vue", "Vue").model_copy(update={"minimum_matches": 2}),
        ],
    )
    receipt = build_evidence_receipt(
        run_id="run-1",
        task_revision_id="revision-1",
        policy=policy,
        capability_id="research.web_search",
        request_input={"query": "React Vue stable releases"},
        result_payload=_web_result(
            "React 20.0 stable release",
            "Vue 4.0 stable release",
        ),
        error=None,
        requirement_id="react",
        source_class_hint="software_release",
    )

    assert receipt is not None
    assert receipt.source_count == 2
    assert receipt.metadata["evidence_source_counts_by_coverage"] == {
        "software_package:react": 1,
        "software_package:vue": 1,
    }
    evidence = evaluate_evidence_set("run-1", policy, [receipt])
    assert evidence.passed is False
    assert {row.requirement_id: row.status for row in evidence.requirements} == {
        "react": "rejected",
        "vue": "rejected",
    }
''',
)

# P1: test doubles must be explicit. Production/default GitHub evidence fails
# closed when the real adapter has not been enabled.
replace_once(
    "src/app/assistant_tools/repo_adapter.py",
    '''_DEFAULT_REPOSITORY_ADAPTER = FakeRepositoryRuntimeAdapter(
    pull_requests={1: RepositoryPullRequestRecord(number=1, title="Prepared change", head_sha="abc123", checks_passed=True)}
)


def get_repository_runtime_adapter() -> RepositoryRuntimeAdapter:
    if (os.environ.get("OMNIX_GITHUB_REAL_ADAPTER") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return GitHubCliRuntimeAdapter()
    return _DEFAULT_REPOSITORY_ADAPTER


def run_repository_tool_request(request: AssistantToolRequest, adapter: RepositoryRuntimeAdapter | None = None) -> AssistantToolResult:
    runtime = adapter or get_repository_runtime_adapter()
    repository = str(request.input.get("repository") or request.input.get("repo") or "")
    try:
''',
    '''def get_repository_runtime_adapter() -> RepositoryRuntimeAdapter:
    if (os.environ.get("OMNIX_GITHUB_REAL_ADAPTER") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return GitHubCliRuntimeAdapter()
    raise RuntimeError("github_runtime_adapter_unavailable")


def run_repository_tool_request(request: AssistantToolRequest, adapter: RepositoryRuntimeAdapter | None = None) -> AssistantToolResult:
    repository = str(request.input.get("repository") or request.input.get("repo") or "")
    try:
        runtime = adapter or get_repository_runtime_adapter()
''',
)

# P1: a failed failure-handler/DB operation must not terminate a dispatcher
# worker. The session queue is still rescheduled in finally.
replace_once(
    "src/app/chat/generation_jobs.py",
    '''            try:
                if work is not None:
                    _run_chat_generation_job(
                        chat_store=work.chat_store,
                        job_store=work.job_store,
                        job=work.job,
                        request=work.request,
                        context_builder=work.context_builder,
                        completion_hook=work.completion_hook,
                    )
            finally:
''',
    '''            try:
                if work is not None:
                    _run_chat_generation_job(
                        chat_store=work.chat_store,
                        job_store=work.job_store,
                        job=work.job,
                        request=work.request,
                        context_builder=work.context_builder,
                        completion_hook=work.completion_hook,
                    )
            except Exception:
                logger.exception(
                    "Unhandled Chat generation worker failure for job %s; worker will continue",
                    getattr(getattr(work, "job", None), "id", "unknown"),
                )
            finally:
''',
)

# P1: a child can complete between approval polls. Terminal reconciliation is
# valid from either running or waiting_for_approval.
def harden_terminal_statuses(region: str) -> str:
    if 'terminal_expected_statuses = ("running", "waiting_for_approval")' not in region:
        region = region.replace(
            '''            if child.status not in {"completed", "failed", "cancelled"}:
                continue

            output: dict[str, Any] = {
''',
            '''            if child.status not in {"completed", "failed", "cancelled"}:
                continue

            terminal_expected_statuses = ("running", "waiting_for_approval")
            output: dict[str, Any] = {
''',
            1,
        )
    return region.replace('expected_statuses=("running",),', 'expected_statuses=terminal_expected_statuses,')

replace_region(
    "src/app/agent_runtime/task_graph_runtime.py",
    '            if child.status not in {"completed", "failed", "cancelled"}:\n                continue\n\n            output: dict[str, Any] = {',
    '    def _claim_node(',
    harden_terminal_statuses,
)

# P2: the browser submission key lives through ambiguous failures (so retries
# dedupe) and rotates immediately after durable acceptance (so an intentional
# repeated prompt is a new turn).
replace_once(
    "src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx",
    '''    onSuccess: (_result, values) => {
      markVoiceTurnPerformance('chatResponseReceivedAt');
      setActiveChatJobId(_result.job.id);
''',
    '''    onSuccess: (_result, values) => {
      markVoiceTurnPerformance('chatResponseReceivedAt');
      if (pendingChatSubmissionRef.current?.id === values.userTurnId) {
        pendingChatSubmissionRef.current = null;
      }
      setActiveChatJobId(_result.job.id);
''',
)
replace_once(
    "src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx",
    '''      setQuickSearchProgress(null);
      setPendingUserMessage(null);
      if (pendingChatSubmissionRef.current?.id === values.userTurnId) {
        pendingChatSubmissionRef.current = null;
      }
      setActiveChatJobId(null);
''',
    '''      setQuickSearchProgress(null);
      setPendingUserMessage(null);
      // Keep the submission identity after an ambiguous transport/server error.
      // Retrying the same payload must reuse the same idempotency key.
      setActiveChatJobId(null);
''',
)

# P2: persist Solana AI decisions as strategy events and expose a first-class
# strategy record + decision-history API. Tests use the in-memory fallback;
# production uses the durable strategy repository.
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''from fastapi import APIRouter, FastAPI, HTTPException, Request

from .service import TradingMarketDataService, default_market_data_service
''',
    '''from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .service import TradingMarketDataService, default_market_data_service
from .strategy_repository import StrategyEvent, TradingStrategyRepository, default_strategy_repository
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''_STATE_KEY = "_omnix_trading_solana_ai_monitor"


def _flag(name: str, default: str = "1") -> bool:
''',
    '''_STATE_KEY = "_omnix_trading_solana_ai_monitor"


class SolanaAIStrategyRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str = SOLANA_AI_STRATEGY_ID
    strategy_version: str = "solana-ai-1m-v1"
    strategy_kind: str = "solana_ai_1m_shadow"
    display_name: str = "Solana AI 1m Shadow"
    instrument_id: str = SOLANA_INSTRUMENT_ID
    binding_id: str = SOLANA_BINDING_ID
    chart_interval: str = "1m"
    mode: str = "shadow"
    configured_enabled: bool
    running: bool
    last_run_at: datetime | None = None
    last_error: str | None = None
    decision_count: int = Field(default=0, ge=0)
    signal_count: int = Field(default=0, ge=0)
    research_only: bool = True
    execution_authority: bool = False


class SolanaAIMonitorControlResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    strategy_id: str = SOLANA_AI_STRATEGY_ID
    running: bool
    configured_enabled: bool
    execution_authority: bool = False


def _default_strategy_repository_factory() -> TradingStrategyRepository | None:
    if os.environ.get("OMNIX_PERSISTENCE_MODE", "").strip() == "legacy_test":
        return None
    return default_strategy_repository()


def _flag(name: str, default: str = "1") -> bool:
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        analyzer_factory: Callable[[], SolanaAIAnalyzer] = SolanaAIAnalyzer,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        interval_seconds: float | None = None,
    ) -> None:
        self.market_service_factory = market_service_factory
        self.analyzer_factory = analyzer_factory
        self.now_factory = now_factory
''',
    '''        analyzer_factory: Callable[[], SolanaAIAnalyzer] = SolanaAIAnalyzer,
        strategy_repository_factory: Callable[[], TradingStrategyRepository | None] = _default_strategy_repository_factory,
        now_factory: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        interval_seconds: float | None = None,
    ) -> None:
        self.market_service_factory = market_service_factory
        self.analyzer_factory = analyzer_factory
        self.strategy_repository_factory = strategy_repository_factory
        self.now_factory = now_factory
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        self.signal_count = 0
        self.error_count = 0

    def start(self) -> None:
''',
    '''        self.signal_count = 0
        self.error_count = 0
        self._decision_events: list[StrategyEvent] = []

    def strategy_record(self) -> SolanaAIStrategyRecord:
        task = self._task
        return SolanaAIStrategyRecord(
            configured_enabled=solana_ai_monitor_enabled(),
            running=bool(task is not None and not task.done()),
            last_run_at=self.last_run_at,
            last_error=self.last_error,
            decision_count=self.decision_count,
            signal_count=self.signal_count,
        )

    def recent_decisions(self, limit: int = 50) -> list[StrategyEvent]:
        normalized_limit = max(1, min(int(limit), 200))
        repository = self.strategy_repository_factory()
        if repository is not None:
            try:
                return [
                    event
                    for event in repository.recent_events(SOLANA_AI_STRATEGY_ID, limit=normalized_limit)
                    if event.event_type == "solana_ai_decision"
                ][:normalized_limit]
            except Exception:
                # Runtime state remains inspectable during a persistence outage;
                # new decisions still fail closed on the write path below.
                pass
        return list(reversed(self._decision_events[-normalized_limit:]))

    def _decision_event(self, payload: dict[str, object], observed_at: datetime) -> StrategyEvent:
        decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
        timestamp = observed_at.astimezone(timezone.utc).isoformat()
        return StrategyEvent(
            strategy_id=SOLANA_AI_STRATEGY_ID,
            event_id=f"solana-ai-decision:{timestamp}",
            instrument_id=SOLANA_INSTRUMENT_ID,
            event_type="solana_ai_decision",
            state=str(decision.get("action") or "unknown"),
            reason_code=None,
            observed_at=observed_at,
            idempotency_key=f"solana-ai-decision:{timestamp}",
            payload=payload,
        )

    def _persist_decision(self, event: StrategyEvent) -> bool:
        repository = self.strategy_repository_factory()
        if repository is None:
            self._decision_events.append(event)
            return False
        persisted = repository.append_event(event)
        self._decision_events.append(event)
        return persisted

    def start(self) -> None:
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        self.last_decision = decision
        self._last_processed_bar_end = latest.end_time
        self.last_error = None
        self.last_provider = result.provider
''',
    '''        self.last_error = None
        self.last_provider = result.provider
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        trade_log("auto_trading", "solana_ai_decision", **payload)
        if decision.action in {"enter_long", "exit_long"}:
            trade_log(
                "auto_trading",
                "solana_ai_signal_observed",
                **payload,
                signal_action=decision.action,
            )
        return 1
''',
    '''        event = self._decision_event(payload, latest.end_time)
        try:
            persisted = self._persist_decision(event)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.error_count += 1
            trade_log(
                "auto_trading",
                "solana_ai_decision_persistence_error",
                strategy_id=SOLANA_AI_STRATEGY_ID,
                instrument_id=SOLANA_INSTRUMENT_ID,
                candle_end=latest.end_time,
                error_type=type(exc).__name__,
                detail=str(exc),
                paper_only=True,
                research_only=True,
                execution_authority=False,
            )
            return 0
        self.last_decision = decision
        self._last_processed_bar_end = latest.end_time
        trade_log("auto_trading", "solana_ai_decision", **payload, decision_persisted=persisted)
        if decision.action in {"enter_long", "exit_long"}:
            trade_log(
                "auto_trading",
                "solana_ai_signal_observed",
                **payload,
                signal_action=decision.action,
                decision_persisted=persisted,
            )
        return 1
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''    @router.post("/stop", status_code=202)
    async def stop_solana_ai_monitor(request: Request) -> dict[str, object]:
''',
    '''    @router.get("/strategy", response_model=SolanaAIStrategyRecord)
    async def solana_ai_strategy(request: Request) -> SolanaAIStrategyRecord:
        return monitor_for(request).strategy_record()

    @router.get("/decisions", response_model=list[StrategyEvent])
    async def solana_ai_decisions(
        request: Request,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[StrategyEvent]:
        return monitor_for(request).recent_decisions(limit)

    @router.post("/stop", status_code=202, response_model=SolanaAIMonitorControlResponse)
    async def stop_solana_ai_monitor(request: Request) -> SolanaAIMonitorControlResponse:
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        return {
            "status": "stopped",
            "strategy_id": SOLANA_AI_STRATEGY_ID,
            "running": False,
            "configured_enabled": solana_ai_monitor_enabled(),
            "execution_authority": False,
        }

    @router.post("/start", status_code=202)
    async def start_solana_ai_monitor(request: Request) -> dict[str, object]:
''',
    '''        return SolanaAIMonitorControlResponse(
            status="stopped",
            running=False,
            configured_enabled=solana_ai_monitor_enabled(),
        )

    @router.post("/start", status_code=202, response_model=SolanaAIMonitorControlResponse)
    async def start_solana_ai_monitor(request: Request) -> SolanaAIMonitorControlResponse:
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''        return {
            "status": "started",
            "strategy_id": SOLANA_AI_STRATEGY_ID,
            "running": True,
            "configured_enabled": solana_ai_monitor_enabled(),
            "execution_authority": False,
        }
''',
    '''        return SolanaAIMonitorControlResponse(
            status="started",
            running=True,
            configured_enabled=solana_ai_monitor_enabled(),
        )
''',
)
replace_once(
    "src/app/trading/strategy_solana_ai_monitor.py",
    '''    "TradingSolanaAIMonitor",
    "create_trading_solana_ai_control_router",
''',
    '''    "SolanaAIMonitorControlResponse",
    "SolanaAIStrategyRecord",
    "TradingSolanaAIMonitor",
    "create_trading_solana_ai_control_router",
''',
)

append_once(
    "src/tests/trading/test_strategy_solana_ai.py",
    "test_solana_ai_monitor_persists_strategy_decision_history",
    r'''

class FixtureStrategyRepository:
    def __init__(self) -> None:
        self.events = []

    def append_event(self, event):
        self.events.append(event)
        return True

    def recent_events(self, strategy_id: str, limit: int = 200):
        assert strategy_id == "solana-ai-1m-shadow"
        return list(reversed(self.events[-limit:]))


def test_solana_ai_monitor_persists_strategy_decision_history() -> None:
    market = FixtureMarket(_bars())
    analyzer = FixtureAnalyzer()
    repository = FixtureStrategyRepository()
    monitor = TradingSolanaAIMonitor(
        market_service_factory=lambda: market,
        analyzer_factory=lambda: analyzer,
        strategy_repository_factory=lambda: repository,
        now_factory=lambda: START + timedelta(minutes=3, seconds=5),
        interval_seconds=2,
    )

    import asyncio

    assert asyncio.run(monitor.run_once()) == 1
    assert len(repository.events) == 1
    event = repository.events[0]
    assert event.strategy_id == "solana-ai-1m-shadow"
    assert event.event_type == "solana_ai_decision"
    assert event.state == "hold"
    assert event.payload["execution_authority"] is False
    assert monitor.recent_decisions()[0].event_id == event.event_id
''',
)

# First-class Solana strategy UI/API integration in the command center.
replace_once(
    "src/apps/web/src/features/trading/tradingStrategyOperationsApi.ts",
    '''export type TradingStrategyOperationsStatus = {
''',
    '''export type SolanaAIStrategyRecord = {
  strategy_id: string;
  strategy_version: string;
  strategy_kind: string;
  display_name: string;
  instrument_id: string;
  binding_id: string;
  chart_interval: string;
  mode: string;
  configured_enabled: boolean;
  running: boolean;
  last_run_at: string | null;
  last_error: string | null;
  decision_count: number;
  signal_count: number;
  research_only: boolean;
  execution_authority: boolean;
};

export type SolanaAIDecisionEvent = {
  strategy_id: string;
  event_id: string;
  instrument_id: string;
  event_type: string;
  state: string;
  observed_at: string;
  payload: Record<string, unknown>;
};

export type TradingStrategyOperationsStatus = {
''',
)
replace_once(
    "src/apps/web/src/features/trading/tradingStrategyOperationsApi.ts",
    '''async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { 'content-type': 'application/json' } });
''',
    '''async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init.headers ?? {}) },
  });
''',
)
replace_once(
    "src/apps/web/src/features/trading/tradingStrategyOperationsApi.ts",
    '''export const tradingStrategyOperationsApi = {
  status: () => requestJson<TradingStrategyOperationsStatus>('/api/trading/strategy-operations/status'),
''',
    '''export const tradingStrategyOperationsApi = {
  status: () => requestJson<TradingStrategyOperationsStatus>('/api/trading/strategy-operations/status'),
  solanaStrategy: () => requestJson<SolanaAIStrategyRecord>('/api/trading/solana-ai/strategy'),
  solanaDecisions: (limit = 20) => requestJson<SolanaAIDecisionEvent[]>(`/api/trading/solana-ai/decisions?limit=${encodeURIComponent(String(limit))}`),
  startSolana: () => requestJson('/api/trading/solana-ai/start', { method: 'POST' }),
  stopSolana: () => requestJson('/api/trading/solana-ai/stop', { method: 'POST' }),
''',
)

replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.tsx",
    '''  type TradingOperationalHealth,
  type TradingStrategyOperationsStatus,
} from './tradingStrategyOperationsApi';
''',
    '''  type SolanaAIDecisionEvent,
  type SolanaAIStrategyRecord,
  type TradingOperationalHealth,
  type TradingStrategyOperationsStatus,
} from './tradingStrategyOperationsApi';
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.tsx",
    '''  const [strategy, setStrategy] = useState<TradingStrategyConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
''',
    '''  const [strategy, setStrategy] = useState<TradingStrategyConfig | null>(null);
  const [solanaStrategy, setSolanaStrategy] = useState<SolanaAIStrategyRecord | null>(null);
  const [solanaDecisions, setSolanaDecisions] = useState<SolanaAIDecisionEvent[]>([]);
  const [solanaControlPending, setSolanaControlPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.tsx",
    '''        const [nextHealth, nextRuntime, nextStrategy] = await Promise.all([
          tradingStrategyOperationsApi.health(accountId),
          tradingStrategyOperationsApi.status(),
          strategyId ? tradingStrategyApi.get(strategyId) : Promise.resolve(null),
        ]);
''',
    '''        const [nextHealth, nextRuntime, nextStrategy, nextSolanaStrategy, nextSolanaDecisions] = await Promise.all([
          tradingStrategyOperationsApi.health(accountId),
          tradingStrategyOperationsApi.status(),
          strategyId ? tradingStrategyApi.get(strategyId) : Promise.resolve(null),
          tradingStrategyOperationsApi.solanaStrategy(),
          tradingStrategyOperationsApi.solanaDecisions(10),
        ]);
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.tsx",
    '''        setRuntime(nextRuntime);
        setStrategy(nextStrategy);
        setError(null);
''',
    '''        setRuntime(nextRuntime);
        setStrategy(nextStrategy);
        setSolanaStrategy(nextSolanaStrategy);
        setSolanaDecisions(nextSolanaDecisions);
        setError(null);
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.tsx",
    '''  const riskReasons = risk?.reason_codes ?? [];
  const systemReasons = health?.reason_codes.filter((reason) => reason !== 'INSTRUMENT_NOT_SELECTED') ?? [];

  return (
''',
    '''  const riskReasons = risk?.reason_codes ?? [];
  const systemReasons = health?.reason_codes.filter((reason) => reason !== 'INSTRUMENT_NOT_SELECTED') ?? [];
  const latestSolanaDecision = solanaDecisions[0];
  const latestSolanaPayload = latestSolanaDecision?.payload?.decision;
  const latestSolanaAction = latestSolanaPayload && typeof latestSolanaPayload === 'object'
    ? String((latestSolanaPayload as Record<string, unknown>).action ?? latestSolanaDecision.state)
    : latestSolanaDecision?.state;

  const toggleSolana = async () => {
    if (!solanaStrategy || solanaControlPending) return;
    setSolanaControlPending(true);
    try {
      if (solanaStrategy.running) await tradingStrategyOperationsApi.stopSolana();
      else await tradingStrategyOperationsApi.startSolana();
      const [nextStrategy, nextDecisions] = await Promise.all([
        tradingStrategyOperationsApi.solanaStrategy(),
        tradingStrategyOperationsApi.solanaDecisions(10),
      ]);
      setSolanaStrategy(nextStrategy);
      setSolanaDecisions(nextDecisions);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSolanaControlPending(false);
    }
  };

  return (
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.tsx",
    '''        <Card
          label="Safety authority"
          value="Paper only"
          detail="Live broker OFF · AI order placement OFF · server risk authority ON"
          state="healthy"
        />
      </div>

      {(systemReasons.length > 0 || riskReasons.length > 0 || paperMonitor?.last_error) ? (
''',
    '''        <Card
          label="Safety authority"
          value="Paper only"
          detail="Live broker OFF · AI order placement OFF · server risk authority ON"
          state="healthy"
        />
        <Card
          label="Solana AI 1m shadow"
          value={solanaStrategy?.running ? 'Running' : solanaStrategy ? 'Stopped' : 'Loading'}
          detail={`${solanaStrategy?.decision_count ?? 0} decisions · latest ${latestSolanaAction ?? 'none'}`}
          state={solanaStrategy?.running ? 'healthy' : solanaStrategy?.configured_enabled ? 'degraded' : 'blocked'}
        />
      </div>

      {solanaStrategy ? (
        <div className="command-center-attention" aria-label="Solana AI strategy history">
          <strong>{solanaStrategy.display_name}</strong>
          <span>
            {solanaStrategy.instrument_id} · {solanaStrategy.chart_interval} · research-only · no execution authority
          </span>
          <button type="button" disabled={solanaControlPending} onClick={() => void toggleSolana()}>
            {solanaControlPending ? 'Updating…' : solanaStrategy.running ? 'Stop shadow monitor' : 'Start shadow monitor'}
          </button>
          <span>
            {solanaDecisions.length
              ? solanaDecisions.slice(0, 5).map((item) => `${time(item.observed_at)} ${item.state}`).join(' · ')
              : 'No persisted Solana decisions yet.'}
          </span>
        </div>
      ) : null}

      {(systemReasons.length > 0 || riskReasons.length > 0 || paperMonitor?.last_error) ? (
''',
)

replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.test.tsx",
    '''const operationsApi = vi.hoisted(() => ({
  health: vi.fn(),
  status: vi.fn(),
}));
''',
    '''const operationsApi = vi.hoisted(() => ({
  health: vi.fn(),
  status: vi.fn(),
  solanaStrategy: vi.fn(),
  solanaDecisions: vi.fn(),
  startSolana: vi.fn(),
  stopSolana: vi.fn(),
}));
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.test.tsx",
    '''      prospective_economic_monitor: monitor,
      universe_archive_monitor: monitor,
''',
    '''      prospective_economic_monitor: monitor,
      solana_ai_monitor: monitor,
      universe_archive_monitor: monitor,
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.test.tsx",
    '''    strategyApi.get.mockResolvedValue(strategy);
  });
''',
    '''    strategyApi.get.mockResolvedValue(strategy);
    operationsApi.solanaStrategy.mockResolvedValue({
      strategy_id: 'solana-ai-1m-shadow',
      strategy_version: 'solana-ai-1m-v1',
      strategy_kind: 'solana_ai_1m_shadow',
      display_name: 'Solana AI 1m Shadow',
      instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
      binding_id: 'binance:websocket_and_rest:crypto:BINANCE:spot:SOL-USDT',
      chart_interval: '1m',
      mode: 'shadow',
      configured_enabled: true,
      running: true,
      last_run_at: '2026-09-04T20:03:00Z',
      last_error: null,
      decision_count: 3,
      signal_count: 1,
      research_only: true,
      execution_authority: false,
    });
    operationsApi.solanaDecisions.mockResolvedValue([
      {
        strategy_id: 'solana-ai-1m-shadow',
        event_id: 'decision-1',
        instrument_id: 'crypto:BINANCE:spot:SOL-USDT',
        event_type: 'solana_ai_decision',
        state: 'hold',
        observed_at: '2026-09-04T20:03:00Z',
        payload: { decision: { action: 'hold', confidence: 60 } },
      },
    ]);
    operationsApi.startSolana.mockResolvedValue({ status: 'started' });
    operationsApi.stopSolana.mockResolvedValue({ status: 'stopped' });
  });
''',
)
replace_once(
    "src/apps/web/src/features/trading/TradingCommandCenter.test.tsx",
    '''    expect(screen.getByText('Paper only')).toBeInTheDocument();
    expect(screen.getByText(/Live broker OFF · AI order placement OFF/)).toBeInTheDocument();
''',
    '''    expect(screen.getByText('Paper only')).toBeInTheDocument();
    expect(screen.getByText('Solana AI 1m Shadow')).toBeInTheDocument();
    expect(screen.getByText(/crypto:BINANCE:spot:SOL-USDT/)).toBeInTheDocument();
    expect(screen.getByText(/3 decisions · latest hold/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop shadow monitor' })).toBeInTheDocument();
    expect(screen.getByText(/Live broker OFF · AI order placement OFF/)).toBeInTheDocument();
''',
)

# Focused regressions for the guard, worker boundary, repository adapter, and
# graph approval terminal reconciliation.
review_tests = ROOT / "src/tests/agent_runtime/test_review_regressions.py"
review_tests.write_text(
    r'''from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace

from app.assistant_tools.models import AssistantToolRequest
from app.assistant_tools.repo_adapter import run_repository_tool_request
from app.chat import generation_jobs


ROOT = Path(__file__).resolve().parents[3]


def test_allow_automatic_does_not_widen_issued_command_capability() -> None:
    source = (ROOT / "src/app/agent_runtime/pi_guard_extension.ts").read_text(encoding="utf-8")
    capability_gate = '!commandAllowedByIssuedCapability && !localCapabilities.has("workspace.command")'
    approval_gate = 'approvalPolicy !== "allow_automatic"'
    assert capability_gate in source
    assert source.index(capability_gate) < source.index(approval_gate, source.index(capability_gate))


def test_repository_evidence_fails_closed_without_real_adapter(monkeypatch) -> None:
    monkeypatch.delenv("OMNIX_GITHUB_REAL_ADAPTER", raising=False)
    result = run_repository_tool_request(
        AssistantToolRequest(
            tool_id="github",
            action_id="github.inspect_ci",
            input={"repository": "does-not-exist/example", "ref": "deadbeef"},
        )
    )
    assert result.error == "github_runtime_adapter_unavailable"
    assert result.output == {}


def test_chat_dispatcher_worker_survives_unhandled_job_failure(monkeypatch) -> None:
    calls: list[str] = []
    second_completed = Event()

    def fake_run_chat_generation_job(**kwargs) -> None:
        job_id = kwargs["job"].id
        calls.append(job_id)
        if job_id == "job-1":
            raise RuntimeError("database failed while recording failure")
        second_completed.set()

    monkeypatch.setattr(generation_jobs, "_run_chat_generation_job", fake_run_chat_generation_job)
    dispatcher = generation_jobs._ChatGenerationDispatcher(worker_count=1)

    def work(job_id: str):
        return generation_jobs._ChatGenerationWork(
            chat_store=object(),
            job_store=object(),
            job=SimpleNamespace(id=job_id, input_payload={"session_id": "chat-1"}),
            request=object(),
            context_builder=None,
            completion_hook=None,
        )

    dispatcher.submit(work("job-1"))
    dispatcher.submit(work("job-2"))

    assert second_completed.wait(timeout=2)
    assert calls == ["job-1", "job-2"]


def test_task_graph_terminal_child_reconciles_from_waiting_for_approval() -> None:
    source = (ROOT / "src/app/agent_runtime/task_graph_runtime.py").read_text(encoding="utf-8")
    terminal_region = source.split(
        'if child.status not in {"completed", "failed", "cancelled"}:', 1
    )[1].split("def _claim_node", 1)[0]
    assert 'terminal_expected_statuses = ("running", "waiting_for_approval")' in terminal_region
    assert 'expected_statuses=("running",),' not in terminal_region
''',
    encoding="utf-8",
)

print("Applied taskgraph review hardening fixes.")
