from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"anchor not found in {path}: {old[:160]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# HTR-12: deterministic source harvesting should be sufficient for obvious,
# fully-resolved primary-source cases. Do not call Hermes merely to have it say
# stop when there is no ambiguity left.
replace(
    "src/app/trading/research/coordinator.py",
    "from .hermes_loop import run_iterative_research\n",
    "from .hermes_loop import ResearchLoopResult, run_iterative_research\n",
)
replace(
    "src/app/trading/research/coordinator.py",
    "def _research_status(*, coverage: ResearchCoverage, actions: list[ResearchActionRecord], evidence_count: int,\n                     stop_reason: str) -> str:\n",
    "def _deterministic_harvest_resolved(coverage: ResearchCoverage, fact_set: TradingFactSet) -> bool:\n"
    "    source_coverage_complete = all(\n"
    "        state == \"complete\"\n"
    "        for state in (coverage.sec, coverage.company_ir, coverage.recent_news)\n"
    "    )\n"
    "    return bool(\n"
    "        source_coverage_complete\n"
    "        and fact_set.catalyst.primary_confirmed\n"
    "        and fact_set.supply_metrics.supply_resolution_status == \"clear\"\n"
    "        and not fact_set.unresolved_facts\n"
    "    )\n\n\n"
    "def _research_status(*, coverage: ResearchCoverage, actions: list[ResearchActionRecord], evidence_count: int,\n                     stop_reason: str) -> str:\n",
)
old_loop = '''    _harvest_action(repository, request, identity, trace_id=trace_id, step=2, operation="web_search", adapter=web,
                    query=f"{identity.symbol} {identity.legal_name or ''} latest catalyst financing warrants", limit=min(6, request.max_sources))
    loop = run_iterative_research(request, identity, repository, planner=planner, sec=sec, company=company, web=web)

    finished = datetime.now(timezone.utc)
'''
new_loop = '''    _harvest_action(repository, request, identity, trace_id=trace_id, step=2, operation="web_search", adapter=web,
                    query=f"{identity.symbol} {identity.legal_name or ''} latest catalyst financing warrants", limit=min(6, request.max_sources))
    harvest_finished = datetime.now(timezone.utc)
    harvest_evidence = repository.list_evidence_as_of(request.instrument_id, harvest_finished, request.max_sources)
    harvest_fact_set = build_fact_set(
        instrument_id=request.instrument_id,
        evidence=harvest_evidence,
        decision_at=harvest_finished,
        strategy_id=request.strategy_id,
    )
    harvest_actions = repository.action_trace(trace_id)
    harvest_coverage = _coverage(harvest_actions, harvest_fact_set, novelty_checked=False)
    if _deterministic_harvest_resolved(harvest_coverage, harvest_fact_set):
        loop = ResearchLoopResult(
            trace_id=f"{trace_id}-resolved",
            planner_backend="not_required",
            stop_reason="deterministic_evidence_complete",
            action_count=0,
            evidence_ids=tuple(item.evidence_id for item in harvest_evidence),
        )
    else:
        loop = run_iterative_research(request, identity, repository, planner=planner, sec=sec, company=company, web=web)

    finished = datetime.now(timezone.utc)
'''
replace("src/app/trading/research/coordinator.py", old_loop, new_loop)

# HTR-13: return a causal decision row for every frozen candidate/setup, not
# only selected trades. This lets outcome persistence retain deterministic,
# research, risk, and execution rejection states with entry/exit only when any.
replace(
    "src/app/trading/strategy_backtest.py",
    "class GapPullbackBacktestSummary(BaseModel):\n",
    '''class GapPullbackBacktestCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: str
    discovery_rank: int | None = None
    decision_at: datetime
    state: str
    rejection_reason: str | None = None
    triggered: bool = False
    quality_score: int | None = Field(default=None, ge=0, le=10)
    selected_trade: bool = False
    entry_time: datetime | None = None
    exit_time: datetime | None = None


class GapPullbackBacktestSummary(BaseModel):
''',
)
replace(
    "src/app/trading/strategy_backtest.py",
    "    trades: tuple[GapPullbackBacktestTrade, ...]\n    summary: GapPullbackBacktestSummary\n",
    "    trades: tuple[GapPullbackBacktestTrade, ...]\n    candidate_decisions: tuple[GapPullbackBacktestCandidateDecision, ...] = ()\n    summary: GapPullbackBacktestSummary\n",
)
replace(
    "src/app/trading/strategy_backtest.py",
    "    attempts: list[_TradeAttempt] = []\n    proposed: list[tuple[object, GapPullbackBacktestTrade]] = []\n",
    "    attempts: list[_TradeAttempt] = []\n    proposed: list[tuple[object, GapPullbackBacktestTrade]] = []\n    decision_by_instrument: dict[str, GapPullbackBacktestCandidateDecision] = {}\n",
)
old_first = '''        attempts.append(attempt)
        if attempt.trade is not None:
            proposed.append((candidate, attempt.trade))
'''
new_first = '''        attempts.append(attempt)
        structure_bars = tuple(resample_final_bars(dataset.bars_by_instrument[candidate.instrument_id], active.structure_interval))
        final_result = evaluate_gap_pullback(candidate, structure_bars, active) if structure_bars else None
        decision_at = structure_bars[-1].end_time if structure_bars else dataset.universe.evaluation_time
        state = final_result.state if final_result is not None else "no_market_data"
        reason = final_result.reason_code if final_result is not None else "NO_MARKET_DATA"
        quality = final_result.features.quality_score if final_result is not None else None
        if attempt.triggered:
            execution_bars = tuple(resample_final_bars(dataset.bars_by_instrument[candidate.instrument_id], active.execution_interval))
            if attempt.trigger_bar_index is not None and attempt.trigger_bar_index < len(execution_bars):
                decision_at = execution_bars[attempt.trigger_bar_index].end_time
            state = "entry_ready"
            reason = attempt.rejection_reason or "FAILED_SELL_OFF_CONFIRMED"
            quality = attempt.trade.quality_score if attempt.trade is not None else quality
        decision_by_instrument[candidate.instrument_id] = GapPullbackBacktestCandidateDecision(
            instrument_id=candidate.instrument_id,
            discovery_rank=candidate.discovery_rank,
            decision_at=decision_at,
            state=state,
            rejection_reason=reason if state != "entry_ready" or attempt.rejection_reason else None,
            triggered=attempt.triggered,
            quality_score=quality,
        )
        if attempt.trade is not None:
            proposed.append((candidate, attempt.trade))
'''
replace("src/app/trading/strategy_backtest.py", old_first, new_first)
replace(
    "src/app/trading/strategy_backtest.py",
    '''            if research_reason is not None:
                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1
                continue
''',
    '''            if research_reason is not None:
                research_rejections[research_reason] = research_rejections.get(research_reason, 0) + 1
                current = decision_by_instrument[proposal.instrument_id]
                decision_by_instrument[proposal.instrument_id] = current.model_copy(update={
                    "decision_at": proposal.entry_time,
                    "state": "research_rejected",
                    "rejection_reason": research_reason,
                    "quality_score": adjusted_quality_score,
                })
                continue
''',
)
replace(
    "src/app/trading/strategy_backtest.py",
    '''        if not decision.allowed:
            risk_rejections[decision.reason_code] = risk_rejections.get(decision.reason_code, 0) + 1
            continue
''',
    '''        if not decision.allowed:
            risk_rejections[decision.reason_code] = risk_rejections.get(decision.reason_code, 0) + 1
            current = decision_by_instrument[proposal.instrument_id]
            decision_by_instrument[proposal.instrument_id] = current.model_copy(update={
                "decision_at": proposal.entry_time,
                "state": "risk_rejected",
                "rejection_reason": decision.reason_code,
                "quality_score": adjusted_quality_score,
            })
            continue
''',
)
replace(
    "src/app/trading/strategy_backtest.py",
    '''        if sized.trade is None:
            if sized.rejection_reason:
                execution_rejections.append(sized.rejection_reason)
            continue
        selected.append(sized.trade.model_copy(update={"quality_score": adjusted_quality_score}))
''',
    '''        if sized.trade is None:
            if sized.rejection_reason:
                execution_rejections.append(sized.rejection_reason)
            current = decision_by_instrument[proposal.instrument_id]
            decision_by_instrument[proposal.instrument_id] = current.model_copy(update={
                "decision_at": proposal.entry_time,
                "state": "execution_rejected",
                "rejection_reason": sized.rejection_reason or "EXECUTION_REJECTED",
                "quality_score": adjusted_quality_score,
            })
            continue
        selected_trade = sized.trade.model_copy(update={"quality_score": adjusted_quality_score})
        selected.append(selected_trade)
        current = decision_by_instrument[proposal.instrument_id]
        decision_by_instrument[proposal.instrument_id] = current.model_copy(update={
            "decision_at": proposal.entry_time,
            "state": "traded",
            "rejection_reason": None,
            "quality_score": adjusted_quality_score,
            "selected_trade": True,
            "entry_time": selected_trade.entry_time,
            "exit_time": selected_trade.exit_time,
        })
''',
)
replace(
    "src/app/trading/strategy_backtest.py",
    '''        trades=tuple(selected),
        summary=summary,
''',
    '''        trades=tuple(selected),
        candidate_decisions=tuple(
            decision_by_instrument[candidate.instrument_id]
            for candidate in dataset.universe.candidates
            if candidate.instrument_id in decision_by_instrument
        ),
        summary=summary,
''',
)

# Persist both labeled trades and unlabeled candidate/setup decisions. Unlabeled
# rows are useful for rejection/coverage analysis but HTR-14 explicitly excludes
# them from promotion sample counts.
replace(
    "src/app/trading/research/outcome_dataset.py",
    '''        "strategy_state": strategy_state,
        "entry_time": entry_time,
''',
    '''        "strategy_state": strategy_state,
        "rejection_reason": rejection_reason,
        "entry_time": entry_time,
''',
)
replace(
    "src/app/trading/research/outcome_dataset.py",
    '''    trades: list[Any] | tuple[Any, ...],
    market_fidelity: str,
''',
    '''    trades: list[Any] | tuple[Any, ...],
    candidate_decisions: list[Any] | tuple[Any, ...] = (),
    market_fidelity: str,
''',
)
replace(
    "src/app/trading/research/outcome_dataset.py",
    '''    saved = 0
    for trade in trades:
''',
    '''    saved = 0
    traded_instruments: set[str] = set()
    for trade in trades:
        traded_instruments.add(trade.instrument_id)
''',
)
replace(
    "src/app/trading/research/outcome_dataset.py",
    '''        saved += int(bool(fact_repository.save_outcome(outcome)))
    return saved
''',
    '''        saved += int(bool(fact_repository.save_outcome(outcome)))

    for decision in candidate_decisions:
        if decision.instrument_id in traded_instruments or getattr(decision, "selected_trade", False):
            continue
        decision_at = decision.decision_at
        features = fact_repository.research_features_as_of(decision.instrument_id, decision_at)
        context = research_context_as_of(
            instrument_id=decision.instrument_id,
            decision_at=decision_at,
            fact_repository=fact_repository,
        )
        research_fidelity = "captured_exact" if features is not None else "unavailable"
        flags = ["unlabeled_non_trade_observation"]
        if features is None:
            flags.append("research_features_unavailable_as_of_decision")
        outcome = build_research_outcome(
            session_date=session_date,
            strategy_id=strategy_id,
            instrument_id=decision.instrument_id,
            strategy_version=strategy_version,
            features=features,
            market_fidelity=market_fidelity,
            research_fidelity=research_fidelity,
            strategy_state=decision.state,
            rejection_reason=decision.rejection_reason,
            entry_time=decision.entry_time,
            exit_time=decision.exit_time,
            data_quality_flags=tuple(flags),
            research_context=context,
        )
        saved += int(bool(fact_repository.save_outcome(outcome)))
    return saved
''',
)

# Make the roadmap-required HTR-13 comparisons explicit in attribution output.
replace(
    "src/app/trading/research/outcome_dataset.py",
    '''    exact = [
        row for row in outcomes
        if row.get("market_fidelity") in {"captured", "captured_point_in_time", "exact", "paper-execution-v2"}
        and row.get("research_fidelity") in {"captured_exact", "exact"}
    ]
    return {
''',
    '''    exact = [
        row for row in outcomes
        if row.get("market_fidelity") in {"captured", "captured_point_in_time", "exact", "paper-execution-v2"}
        and row.get("research_fidelity") in {"captured_exact", "exact"}
    ]
    structure_only = [row for row in outcomes if str(row.get("strategy_version") or "") in {"1.0.0", "1.1.0"}]
    same_day_primary = [
        row for row in outcomes
        if (row.get("features") or {}).get("primary_catalyst_confirmed") is True
        and (row.get("features") or {}).get("catalyst_same_day") is True
    ]
    secondary_only = [
        row for row in outcomes
        if (row.get("features") or {}).get("primary_catalyst_confirmed") is False
        and int(((((row.get("features") or {}).get("_research_context") or {}).get("catalyst") or {}).get("source_count_secondary") or 0)) > 0
    ]
    resolved_supply = [row for row in outcomes if (row.get("features") or {}).get("supply_resolution_status") == "clear"]
    unresolved_supply_rows = [row for row in outcomes if (row.get("features") or {}).get("supply_resolution_status") == "unresolved"]
    strategy_states = {
        state: _group_stats([row for row in outcomes if str(row.get("strategy_state") or "unavailable") == state])
        for state in sorted({str(row.get("strategy_state") or "unavailable") for row in outcomes})
    }
    return {
''',
)
replace(
    "src/app/trading/research/outcome_dataset.py",
    '''        "baseline": _group_stats(outcomes),
        "exact_causal_subset": _group_stats(exact),
''',
    '''        "baseline": _group_stats(outcomes),
        "structure_only_baseline": _group_stats(structure_only),
        "exact_causal_subset": _group_stats(exact),
        "same_day_primary_vs_secondary_only": {
            "same_day_primary": _group_stats(same_day_primary),
            "secondary_only": _group_stats(secondary_only),
        },
        "supply_resolution": {
            "clear": _group_stats(resolved_supply),
            "unresolved": _group_stats(unresolved_supply_rows),
        },
        "strategy_states": strategy_states,
''',
)

# Route persistence must pass candidate decisions and must persist zero-trade
# days as observational HTR-13 rows too.
replace(
    "src/app/trading/strategy_api.py",
    '''                    trades=result.trades,
                    market_fidelity="captured_point_in_time",
''',
    '''                    trades=result.trades,
                    candidate_decisions=result.candidate_decisions,
                    market_fidelity="captured_point_in_time",
''',
)
replace(
    "src/app/trading/strategy_api.py",
    '''                if day.result is not None and day.result.trades:
''',
    '''                if day.result is not None and day.result.candidate_decisions:
''',
)
replace(
    "src/app/trading/strategy_api.py",
    '''                            trades=day.result.trades,
                            market_fidelity=(
''',
    '''                            trades=day.result.trades,
                            candidate_decisions=day.result.candidate_decisions,
                            market_fidelity=(
''',
)

# Regression coverage for HTR-12 zero-call rule and HTR-13 candidate completeness.
foundation = Path("src/tests/trading/test_trading_research_htr15_completion.py")
text = foundation.read_text(encoding="utf-8")
if "test_backtest_returns_decision_row_for_every_candidate" not in text:
    text += '''\n\ndef test_backtest_returns_decision_row_for_every_candidate() -> None:\n    triggered = "equity:NASDAQ:AAA"\n    rejected = "equity:NASDAQ:ZZZ"\n    candidates = [_candidate(triggered, 1), _candidate(rejected, 2).model_copy(update={"gap_pct": Decimal("5")})]\n    universe = freeze_gapper_universe(\n        universe_id="htr-candidate-outcomes-2026-08-18",\n        session_date=date(2026, 8, 18),\n        evaluation_time=datetime(2026, 8, 18, 13, 20, tzinfo=timezone.utc),\n        discovery_source="import",\n        candidates=candidates,\n    )\n    dataset = freeze_backtest_session(\n        session_date=date(2026, 8, 18),\n        universe=universe,\n        bars_by_instrument={triggered: _bars(triggered), rejected: _bars(rejected)},\n    )\n    result = run_gap_pullback_backtest(\n        dataset,\n        GapPullbackConfig(pivot_left_bars=1, pivot_right_bars=1, volume_lookback_bars=5, entry_start_et=time(9, 30)),\n        PaperExecutionPolicy(slippage_bps=Decimal("10"), max_volume_participation_pct=Decimal("1"), latency_ms=0),\n    )\n    assert len(result.candidate_decisions) == 2\n    by_symbol = {item.instrument_id: item for item in result.candidate_decisions}\n    assert by_symbol[triggered].triggered is True\n    assert by_symbol[rejected].state == "rejected"\n    assert by_symbol[rejected].selected_trade is False\n\n\ndef test_deterministic_harvest_resolution_rule_skips_only_fully_resolved_primary_case() -> None:\n    from app.trading.research.contracts import ResearchCoverage\n    from app.trading.research.coordinator import _deterministic_harvest_resolved\n    from app.trading.research.facts.extraction import build_fact_set\n    from app.trading.research.contracts import TradingEvidence, fingerprint\n\n    captured = datetime(2026, 8, 20, 13, 30, tzinfo=timezone.utc)\n    catalyst = TradingEvidence(\n        evidence_id="ir-catalyst", instrument_id="equity:NASDAQ:XYZ", evidence_type="company_release",\n        source_type="company_ir", source_locator="https://example.test/ir", source_authority_tier=1,\n        source_published_at=captured, source_available_at=captured, captured_at=captured, omnix_known_at=captured,\n        title="Company announces contract award", content="The company announced a material contract award today.",\n        content_hash="c" * 64, extraction_status="completed", metadata={},\n        immutable_fingerprint=fingerprint({"id": "ir-catalyst"}),\n    )\n    supply = TradingEvidence(\n        evidence_id="sec-supply", instrument_id="equity:NASDAQ:XYZ", evidence_type="sec_filing_content",\n        source_type="sec", source_locator="https://sec.gov/Archives/example", source_authority_tier=1,\n        source_published_at=captured, source_available_at=captured, captured_at=captured, omnix_known_at=captured,\n        title="ATM termination", content="The previous at-the-market offering was terminated and is no longer available.",\n        content_hash="d" * 64, extraction_status="completed", metadata={"form": "8-K"},\n        immutable_fingerprint=fingerprint({"id": "sec-supply"}),\n    )\n    facts = build_fact_set(instrument_id="equity:NASDAQ:XYZ", evidence=(catalyst, supply), decision_at=captured)\n    complete = ResearchCoverage(sec="complete", company_ir="complete", recent_news="complete")\n    assert _deterministic_harvest_resolved(complete, facts) is True\n    assert _deterministic_harvest_resolved(complete.model_copy(update={"sec": "failed"}), facts) is False\n'''
    foundation.write_text(text, encoding="utf-8")

print("Final HTR roadmap completion patch applied.")
