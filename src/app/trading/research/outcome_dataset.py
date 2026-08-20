from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .contracts import ResearchOutcome, StrategyResearchFeatures, fingerprint


def build_research_outcome(*, session_date: date, instrument_id: str, strategy_version: str,
                           features: StrategyResearchFeatures | None, strategy_id: str | None=None,
                           market_fidelity: str="captured", research_fidelity: str="captured_exact",
                           strategy_state: str | None=None, rejection_reason: str | None=None,
                           entry_time: datetime | None=None, exit_time: datetime | None=None,
                           mfe_r: Decimal | None=None, mae_r: Decimal | None=None, r_result: Decimal | None=None,
                           two_r_before_minus_one_r: bool | None=None, time_to_mfe_minutes: Decimal | None=None,
                           time_to_stop_minutes: Decimal | None=None, data_quality_flags: tuple[str,...]=()) -> ResearchOutcome:
    feature_payload=features.model_dump(mode="json") if features else {}
    research_policy=features.research_policy_version if features else "unavailable"
    projection=features.projection_version if features else "unavailable"
    research_status=features.research_status if features else "unavailable"
    payload={"session_date":session_date.isoformat(),"instrument_id":instrument_id,"strategy_version":strategy_version,
             "features":feature_payload,"strategy_state":strategy_state,"entry_time":entry_time,"exit_time":exit_time,
             "mfe_r":mfe_r,"mae_r":mae_r,"r_result":r_result,"market_fidelity":market_fidelity,"research_fidelity":research_fidelity}
    fp=fingerprint(payload)
    return ResearchOutcome(outcome_id=f"rout-{hashlib.sha256((instrument_id+'|'+fp).encode()).hexdigest()[:24]}",session_date=session_date,
        strategy_id=strategy_id,instrument_id=instrument_id,strategy_version=strategy_version,research_policy_version=research_policy,
        feature_projection_version=projection,market_fidelity=market_fidelity,research_fidelity=research_fidelity,research_status=research_status,
        features=feature_payload,strategy_state=strategy_state,rejection_reason=rejection_reason,entry_time=entry_time,exit_time=exit_time,
        mfe_r=mfe_r,mae_r=mae_r,r_result=r_result,two_r_before_minus_one_r=two_r_before_minus_one_r,
        time_to_mfe_minutes=time_to_mfe_minutes,time_to_stop_minutes=time_to_stop_minutes,data_quality_flags=data_quality_flags,
        immutable_fingerprint=fp)


def attribution_summary(outcomes: list[dict[str,Any]]) -> dict[str,Any]:
    def dec(v): return Decimal(str(v)) if v is not None else None
    valid=[o for o in outcomes if dec(o.get("r_result")) is not None]
    baseline=(sum((dec(o["r_result"]) or Decimal("0") for o in valid),Decimal("0"))/Decimal(len(valid))) if valid else None
    comparisons={}
    keys=("primary_catalyst_confirmed","catalyst_same_day","immediate_supply_risk","unresolved_supply","source_authority_sufficient")
    for key in keys:
        yes=[dec(o.get("r_result")) for o in valid if (o.get("features") or {}).get(key) is True]
        no=[dec(o.get("r_result")) for o in valid if (o.get("features") or {}).get(key) is False]
        comparisons[key]={"true_n":len(yes),"false_n":len(no),"true_expectancy_r":sum(yes,Decimal("0"))/Decimal(len(yes)) if yes else None,
                          "false_expectancy_r":sum(no,Decimal("0"))/Decimal(len(no)) if no else None}
    return {"sample_size":len(outcomes),"labeled_sample_size":len(valid),"baseline_expectancy_r":baseline,"comparisons":comparisons}
