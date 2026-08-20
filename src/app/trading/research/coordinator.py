from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict

from app.trading.trade_logging import trade_log

from .adapters.company_ir import CompanyIrAdapter
from .adapters.generic_web import GenericWebAdapter
from .adapters.sec_edgar import SecEdgarAdapter
from .contracts import (
    ResearchActionRecord, ResearchCoverage, StrategyResearchFeatures, TradingFactSet, TradingResearchReport,
    TradingResearchRequest, fingerprint,
)
from .fact_repository import TradingFactRepository, default_fact_repository
from .facts.extraction import build_fact_set
from .feature_projection import project_research_features
from .hermes_loop import run_iterative_research
from .issuer_identity import SecIssuerIdentityResolver
from .novelty_shadow import generate_novelty_shadow
from .repository import TradingResearchRepository, default_research_repository
from .shadow_repository import TradingShadowResearchRepository, default_shadow_repository


class TradingResearchCoordinatorResult(BaseModel):
    model_config=ConfigDict(extra="forbid",frozen=True)
    request: TradingResearchRequest
    report: TradingResearchReport
    fact_set: TradingFactSet
    features: StrategyResearchFeatures
    trace_id: str
    planner_backend: str
    warnings: tuple[str,...]=()


def create_trading_research_request(*, instrument_id: str, strategy_id: str | None=None, decision_context_at: datetime | None=None,
                                    deadline_seconds: int=45, max_steps: int=8, max_queries: int=5, max_sources: int=20, max_extracts: int=8,
                                    objectives: tuple[str,...]=("catalyst_identity","catalyst_novelty","financing","atm","warrant_overhang","resale_registration","convertibles")) -> TradingResearchRequest:
    now=datetime.now(timezone.utc); decision=decision_context_at.astimezone(timezone.utc) if decision_context_at else now
    rid="trq-"+hashlib.sha256(f"{instrument_id}|{strategy_id}|{now.isoformat()}".encode()).hexdigest()[:24]
    return TradingResearchRequest(request_id=rid,strategy_id=strategy_id,instrument_id=instrument_id,requested_at=now,
        decision_context_at=decision,evidence_cutoff_at=now,objectives=objectives,deadline_at=now+timedelta(seconds=max(5,deadline_seconds)),
        max_steps=max_steps,max_queries=max_queries,max_sources=max_sources,max_extracts=max_extracts)


def _harvest_action(repository: TradingResearchRepository, request: TradingResearchRequest, identity, *, trace_id: str, step: int, operation: str, adapter, query: str | None, limit: int) -> tuple[str,...]:
    started=datetime.now(timezone.utc); action_id="harvest-"+hashlib.sha256(f"{trace_id}|{step}|{operation}".encode()).hexdigest()[:24]
    try:
        result=adapter.find(identity,query=query,limit=limit); existing=repository.list_evidence_as_of(request.instrument_id,datetime.now(timezone.utc),request.max_sources)
        remaining=max(0,request.max_sources-len(existing)); ids=[]
        for item in result.evidence[:remaining]: ids.append(repository.save_evidence(item).evidence_id)
        completed=datetime.now(timezone.utc)
        repository.save_action(ResearchActionRecord(action_id=action_id,trace_id=trace_id,strategy_id=request.strategy_id,instrument_id=request.instrument_id,
            step=step,operation=operation,args={"query":query or "","limit":limit},reason="deterministic_primary_source_harvest",status="completed",
            result_summary={"detail":result.detail,"evidence_count":len(ids)},evidence_ids=tuple(ids),requested_at=started,completed_at=completed,
            immutable_fingerprint=fingerprint({"trace":trace_id,"step":step,"operation":operation,"ids":ids})))
        return tuple(ids)
    except Exception as exc:
        completed=datetime.now(timezone.utc)
        repository.save_action(ResearchActionRecord(action_id=action_id,trace_id=trace_id,strategy_id=request.strategy_id,instrument_id=request.instrument_id,
            step=step,operation=operation,args={"query":query or "","limit":limit},reason="deterministic_primary_source_harvest",status="failed",
            result_summary={},evidence_ids=(),requested_at=started,completed_at=completed,error_code=type(exc).__name__,
            immutable_fingerprint=fingerprint({"trace":trace_id,"step":step,"operation":operation,"error":type(exc).__name__})))
        return ()


def _coverage(actions: list[ResearchActionRecord], fact_set: TradingFactSet, novelty_checked: bool) -> ResearchCoverage:
    complete={a.operation for a in actions if a.status=="completed"}; failed={a.operation for a in actions if a.status=="failed"}
    def source(op): return "complete" if op in complete else "failed" if op in failed else "unchecked"
    sec=source("sec_find_filings"); ir=source("company_find_releases"); news=source("web_search")
    by_type={}
    for fact in fact_set.supply: by_type.setdefault(fact.supply_type,[]).append(fact)
    def supply(kind):
        values=by_type.get(kind,[])
        if any(x.resolution_status=="unresolved" for x in values): return "unresolved"
        if sec=="complete": return "complete"
        return "failed" if sec=="failed" else "unchecked"
    return ResearchCoverage(sec=sec,company_ir=ir,recent_news=news,prior_news_novelty="complete" if novelty_checked else "unchecked",
        atm=supply("atm"),warrants=supply("warrant"),resale_registration=supply("resale_registration"),convertibles=supply("convertible"))


def run_trading_research(request: TradingResearchRequest, *, repository: TradingResearchRepository | None=None,
                         fact_repository: TradingFactRepository | None=None, shadow_repository: TradingShadowResearchRepository | None=None,
                         identity_resolver=None, sec=None, web=None, company=None, planner=None, run_shadow_ai: bool=True) -> TradingResearchCoordinatorResult:
    repository=repository or default_research_repository(); fact_repository=fact_repository or default_fact_repository(); shadow_repository=shadow_repository or default_shadow_repository()
    identity_resolver=identity_resolver or SecIssuerIdentityResolver(); sec=sec or SecEdgarAdapter(); web=web or GenericWebAdapter(); company=company or CompanyIrAdapter(web)
    now=datetime.now(timezone.utc); identity=repository.identity_as_of(request.instrument_id,now)
    if identity is None: identity=repository.save_identity(identity_resolver.resolve(request.instrument_id))
    trace_id="htr-harvest-"+hashlib.sha256(request.request_id.encode()).hexdigest()[:20]
    _harvest_action(repository,request,identity,trace_id=trace_id,step=0,operation="sec_find_filings",adapter=sec,query="8-K,10-Q,10-K,S-1,S-1/A,S-3,S-3/A,424B3,424B5,RW,EFFECT",limit=min(12,request.max_sources))
    _harvest_action(repository,request,identity,trace_id=trace_id,step=1,operation="company_find_releases",adapter=company,query=None,limit=min(6,request.max_sources))
    _harvest_action(repository,request,identity,trace_id=trace_id,step=2,operation="web_search",adapter=web,query=f"{identity.symbol} {identity.legal_name or ''} latest catalyst financing warrants",limit=min(6,request.max_sources))
    loop=run_iterative_research(request,identity,repository,planner=planner,sec=sec,company=company,web=web)
    finished=datetime.now(timezone.utc); evidence=repository.list_evidence_as_of(request.instrument_id,finished,request.max_sources)
    preliminary=build_fact_set(instrument_id=request.instrument_id,evidence=evidence,decision_at=finished,strategy_id=request.strategy_id)
    novelty_checked=False; warnings=list(loop.warnings)
    if run_shadow_ai:
        try:
            annotation=generate_novelty_shadow(request.instrument_id,evidence,observed_at=finished); shadow_repository.save(annotation); novelty_checked=True
        except Exception as exc: warnings.append(f"novelty_shadow_unavailable:{type(exc).__name__}")
    actions=repository.action_trace(trace_id)+repository.action_trace(loop.trace_id)
    coverage=_coverage(actions,preliminary,novelty_checked)
    fact_preview=build_fact_set(instrument_id=request.instrument_id,evidence=evidence,decision_at=finished,strategy_id=request.strategy_id,coverage=coverage)
    immediate=fact_preview.supply_metrics.immediate_supply_risk
    catalyst_status="confirmed" if fact_preview.catalyst.primary_confirmed else "probable" if fact_preview.catalyst.source_evidence_ids else "unresolved"
    supply_status="risk_found" if immediate else "clear" if fact_preview.supply_metrics.supply_resolution_status=="clear" else "unresolved"
    states=coverage.model_dump(); complete=all(value=="complete" for value in states.values())
    research_status="complete" if complete else "partial"
    version=repository.next_report_version(request.instrument_id)
    report_payload={"version":version,"instrument_id":request.instrument_id,"evidence_ids":[x.evidence_id for x in evidence],"coverage":states,
                    "catalyst_status":catalyst_status,"supply_status":supply_status,"research_status":research_status,"trace":loop.trace_id}
    report=repository.save_report(TradingResearchReport(report_id=f"trr-{hashlib.sha256((request.instrument_id+'|'+str(version)+'|'+fingerprint(report_payload)).encode()).hexdigest()[:24]}",
        report_version=version,strategy_id=request.strategy_id,instrument_id=request.instrument_id,research_started_at=request.requested_at,
        research_completed_at=finished,evidence_cutoff_at=finished,catalyst_status=catalyst_status,supply_status=supply_status,research_status=research_status,
        coverage=coverage,unresolved_facts=fact_preview.unresolved_facts,source_evidence_ids=tuple(x.evidence_id for x in evidence),hermes_trace_id=loop.trace_id,
        planner_backend=loop.planner_backend,stop_reason=loop.stop_reason,immutable_fingerprint=fingerprint(report_payload)))
    # Rebuild after the immutable report exists so report_id participates in the
    # fact-set fingerprint. Report v1/v2/v3 can therefore never alias the same
    # durable fact-set identity just because their extracted values are equal.
    fact_set=build_fact_set(instrument_id=request.instrument_id,evidence=evidence,decision_at=finished,strategy_id=request.strategy_id,
                            report_id=report.report_id,coverage=coverage)
    saved_supply=tuple(fact_repository.save_supply_fact(item) for item in fact_set.supply)
    fact_set=fact_set.model_copy(update={"supply":saved_supply})
    fact_set=fact_repository.save_fact_set(fact_set)
    decision_at=max(finished,fact_set.omnix_known_at or finished)
    features=fact_repository.save_features(project_research_features(fact_set,decision_at=decision_at,report=report))
    trade_log("auto_trading","trading_research_completed",trace_id=loop.trace_id,strategy_id=request.strategy_id,instrument_id=request.instrument_id,
              report_id=report.report_id,report_version=report.report_version,fact_set_id=fact_set.fact_set_id,feature_id=features.feature_id,
              omnix_known_at=features.omnix_known_at,coverage=coverage,unresolved_facts=fact_set.unresolved_facts,warnings=warnings)
    return TradingResearchCoordinatorResult(request=request,report=report,fact_set=fact_set,features=features,trace_id=loop.trace_id,
        planner_backend=loop.planner_backend,warnings=tuple(dict.fromkeys(warnings)))
