from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .contracts import ResearchValidationReport, ValidationFeatureResult, fingerprint

_FEATURES=("primary_catalyst_confirmed","catalyst_same_day","immediate_supply_risk","unresolved_supply","source_authority_sufficient")


def _r(row):
    value=row.get("r_result"); return Decimal(str(value)) if value is not None else None


def _mean(values): return sum(values,Decimal("0"))/Decimal(len(values)) if values else None


def _effect(rows,key):
    yes=[_r(x) for x in rows if (x.get("features") or {}).get(key) is True and _r(x) is not None]
    no=[_r(x) for x in rows if (x.get("features") or {}).get(key) is False and _r(x) is not None]
    if not yes or not no:return None
    direction=Decimal("-1") if key in {"immediate_supply_risk","unresolved_supply"} else Decimal("1")
    return (_mean(yes)-_mean(no))*direction


def build_validation_report(outcomes: list[dict[str,Any]], *, policy_version: str="trading-research-1",
                            minimum_sample: int=100, minimum_exact_sample: int=50) -> ResearchValidationReport:
    # Repository returns newest-first; reverse to make a deterministic chronological
    # holdout where the newest ~30% is out-of-sample.
    chronological=list(reversed(outcomes)); cut=max(1,int(len(chronological)*0.7)) if chronological else 0
    train=chronological[:cut]; test=chronological[cut:]
    exact=[x for x in outcomes if x.get("market_fidelity") in {"captured","captured_point_in_time","exact"} and x.get("research_fidelity") in {"captured_exact","exact"}]
    results=[]
    for key in _FEATURES:
        ins=_effect(train,key); outs=_effect(test,key); n=sum(1 for x in outcomes if key in (x.get("features") or {})); exact_n=sum(1 for x in exact if key in (x.get("features") or {}))
        recommendation="observe_only"; reason="insufficient causal outcome evidence"
        # Promotion is intentionally conservative: both chronological segments,
        # overall and exact sample thresholds, and positive effect are required.
        if n>=minimum_sample and exact_n>=minimum_exact_sample and ins is not None and outs is not None and ins>Decimal("0.10") and outs>Decimal("0.10"):
            recommendation="score_only"; reason="positive in/out-of-sample effect; begin deterministic scoring validation"
        results.append(ValidationFeatureResult(feature=key,sample_size=n,exact_sample_size=exact_n,in_sample_effect_r=ins,out_of_sample_effect_r=outs,
            recommendation=recommendation,reason=reason))
    # HTR-14 never promotes directly to execution authority. A later reviewed
    # report may be explicitly amended/created with soft/hard-gate recommendation.
    promotion=False
    generated=datetime.now(timezone.utc); payload={"policy":policy_version,"sample":len(outcomes),"exact":len(exact),"results":[x.model_dump(mode="json") for x in results],"promotion":promotion}
    fp=fingerprint(payload)
    return ResearchValidationReport(validation_id=f"rval-{hashlib.sha256(fp.encode()).hexdigest()[:24]}",policy_version=policy_version,generated_at=generated,
        sample_size=len(outcomes),exact_sample_size=len(exact),feature_results=tuple(results),promotion_allowed=promotion,
        notes=("Automatic HTR-14 analysis cannot grant execution authority; explicit reviewed promotion is required.",),immutable_fingerprint=fp)
