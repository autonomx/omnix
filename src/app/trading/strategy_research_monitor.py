from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from .research.coordinator import create_trading_research_request, run_trading_research
from .research.repository import default_research_repository
from .strategy_repository import TradingStrategyRepository, default_strategy_repository
from .trade_logging import trade_log
from .us_equity_calendar import regular_holidays

_ET=ZoneInfo("America/New_York")
_STATE_KEY="_omnix_trading_strategy_research_monitor"


def _flag(name: str,default: str="1") -> bool: return os.environ.get(name,default).strip().lower() in {"1","true","yes","on"}

def strategy_research_monitor_enabled() -> bool:
    if os.environ.get("OMNIX_PERSISTENCE_MODE","").strip()=="legacy_test": return _flag("OMNIX_TRADING_RESEARCH_MONITOR_IN_TESTS","0")
    return _flag("OMNIX_TRADING_RESEARCH_MONITOR","1")

def _interval_seconds() -> float:
    try:value=float(os.environ.get("OMNIX_TRADING_RESEARCH_MONITOR_INTERVAL_SECONDS","60"))
    except ValueError:value=60.0
    return max(15.0,value)


def _plausible(config,candidate) -> bool:
    rules=config.config
    if candidate.gap_pct<rules.minimum_gap_pct:return False
    if not rules.minimum_price<=candidate.premarket_price<=rules.maximum_price:return False
    if candidate.premarket_dollar_volume<rules.minimum_premarket_dollar_volume:return False
    if candidate.tod_rvol is not None and candidate.tod_rvol<rules.minimum_tod_rvol:return False
    if candidate.spread_bps is not None and candidate.spread_bps>rules.maximum_spread_bps:return False
    return True


class TradingStrategyResearchMonitor:
    """Evidence-only research funnel; has no order/config/universe mutation path."""
    def __init__(self,*,interval_seconds:float|None=None,max_candidates_per_strategy:int=5) -> None:
        self.interval_seconds=interval_seconds or _interval_seconds();self.max_candidates_per_strategy=max(1,min(10,max_candidates_per_strategy));self._task=None
        self.last_run_at:datetime|None=None;self.last_error:str|None=None;self.research_count=0

    def start(self)->None:
        if self._task is None:self._task=asyncio.create_task(self._loop())
    async def stop(self)->None:
        task=self._task;self._task=None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):await task

    async def run_once(self)->int:
        strategy_repo:TradingStrategyRepository=default_strategy_repository();research_repo=default_research_repository();now=datetime.now(timezone.utc);now_et=now.astimezone(_ET)
        if now_et.weekday()>=5 or now_et.date() in regular_holidays(now_et.year):self.last_run_at=now;return 0
        configs=await asyncio.to_thread(strategy_repo.list_configs,active_only=False);completed=0
        for config in configs:
            if not config.enabled or not config.config.auto_archive_daily_universe:continue
            scan=config.config.universe_scan_time_et
            if now_et.time()<scan or now_et.time()>max(config.config.last_entry_et,time(12,0)):continue
            universes=await asyncio.to_thread(strategy_repo.list_universes,start_date=now_et.date(),end_date=now_et.date())
            eligible=[u for u in universes if u.universe_id.startswith("auto-archive-") and u.evaluation_time<=now]
            if not eligible:continue
            universe=max(eligible,key=lambda u:u.evaluation_time)
            candidates=sorted((c for c in universe.candidates if _plausible(config,c)),key=lambda c:(c.discovery_rank if c.discovery_rank is not None else 10**9,-float(c.gap_pct)))[:self.max_candidates_per_strategy]
            for candidate in candidates:
                try:
                    timeline=await asyncio.to_thread(research_repo.report_timeline,candidate.instrument_id,20)
                    already=any(r.omnix_known_at and r.omnix_known_at.astimezone(_ET).date()==now_et.date() and r.strategy_id==config.strategy_id for r in timeline)
                    if already:continue
                    request=create_trading_research_request(instrument_id=candidate.instrument_id,strategy_id=config.strategy_id,decision_context_at=now,
                        deadline_seconds=45,max_steps=8,max_queries=5,max_sources=20,max_extracts=8)
                    result=await asyncio.to_thread(run_trading_research,request)
                    completed+=1
                    trade_log("auto_trading","morning_trading_research_completed",strategy_id=config.strategy_id,instrument_id=candidate.instrument_id,
                        universe_id=universe.universe_id,trace_id=result.trace_id,report_id=result.report.report_id,report_version=result.report.report_version,
                        research_status=result.report.research_status,coverage=result.report.coverage,unresolved_facts=result.report.unresolved_facts,execution_authority=False)
                except Exception as exc:
                    self.last_error=f"{config.strategy_id}/{candidate.instrument_id}: {type(exc).__name__}: {exc}"
                    trade_log("auto_trading","morning_trading_research_error",strategy_id=config.strategy_id,instrument_id=candidate.instrument_id,
                        universe_id=universe.universe_id,error_type=type(exc).__name__,detail=str(exc),execution_authority=False)
        self.research_count+=completed;self.last_run_at=datetime.now(timezone.utc);return completed

    async def _loop(self)->None:
        while True:
            try:await self.run_once()
            except Exception as exc:
                self.last_error=f"{type(exc).__name__}: {exc}";trade_log("auto_trading","trading_research_monitor_error",error_type=type(exc).__name__,detail=str(exc),execution_authority=False)
            await asyncio.sleep(self.interval_seconds)


def register_trading_strategy_research_monitor(gateway:FastAPI)->TradingStrategyResearchMonitor:
    existing=getattr(gateway.state,_STATE_KEY,None)
    if isinstance(existing,TradingStrategyResearchMonitor):return existing
    monitor=TradingStrategyResearchMonitor();setattr(gateway.state,_STATE_KEY,monitor)
    async def startup():
        if strategy_research_monitor_enabled():monitor.start()
    async def shutdown():await monitor.stop()
    gateway.router.add_event_handler("startup",startup);gateway.router.add_event_handler("shutdown",shutdown);return monitor


__all__=["TradingStrategyResearchMonitor","register_trading_strategy_research_monitor","strategy_research_monitor_enabled"]
