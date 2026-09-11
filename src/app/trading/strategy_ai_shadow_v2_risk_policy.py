from __future__ import annotations

"""Deterministic risk policy for AI Shadow v2.

The alpha model may choose an invalidation level, but it cannot make an extremely
wide stop acceptable merely by proposing an equally distant target. Minimum-R
math also keeps the configured worst-case allowed spread + slippage assumption;
point-in-time spread remains a separate execution gate and never relaxes 2R.
"""

from decimal import Decimal

from . import strategy_ai_shadow_v2_hardening as hardening
from . import strategy_ai_shadow_v2_monitor as monitor

AI_SHADOW_V2_MAX_STRUCTURAL_RISK_PCT = Decimal("8")
_INSTALLED = False
_ORIGINAL_RISK_GEOMETRY = None


def _risk_geometry_policy(
    decision,
    *,
    entry_reference: Decimal,
    estimated_cost_bps: Decimal,
    minimum_net_r: Decimal,
):
    assert _ORIGINAL_RISK_GEOMETRY is not None
    geometry = _ORIGINAL_RISK_GEOMETRY(
        decision,
        entry_reference=entry_reference,
        estimated_cost_bps=estimated_cost_bps,
        minimum_net_r=minimum_net_r,
    )
    if geometry.risk_per_share is None or entry_reference <= 0:
        return geometry
    risk_pct = geometry.risk_per_share / entry_reference * Decimal("100")
    if risk_pct <= AI_SHADOW_V2_MAX_STRUCTURAL_RISK_PCT:
        return geometry
    return geometry.model_copy(
        update={
            "valid": False,
            "reason": "maximum_structural_risk_pct_exceeded",
        }
    )


def install_ai_shadow_v2_risk_policy() -> None:
    global _INSTALLED, _ORIGINAL_RISK_GEOMETRY
    if _INSTALLED:
        return
    # Hardening previously introduced an observed-spread optimization. The
    # roadmap requires minimum acceptable R to remain unchanged, so bind the
    # authoritative geometry to the pre-optimization deterministic function.
    _ORIGINAL_RISK_GEOMETRY = hardening._ORIGINAL_RISK_GEOMETRY
    monitor.deterministic_risk_geometry = _risk_geometry_policy
    _INSTALLED = True


__all__ = [
    "AI_SHADOW_V2_MAX_STRUCTURAL_RISK_PCT",
    "install_ai_shadow_v2_risk_policy",
]
