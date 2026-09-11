"""Native Omnix Trading domain."""

from .models import (
    CanonicalInstrument,
    DatasetProvenance,
    MarketBar,
    ProviderBinding,
    ProviderPolicy,
)
from .ai_shadow_reliability import install_ai_shadow_reliability
from .ai_shadow_circuit_persistence import install_persistent_ai_shadow_circuit
from .trading_data_hardening import install_trading_data_hardening
from .trading_data_runtime_refinements import install_trading_data_runtime_refinements
from .trading_session_reliability import install_trading_session_reliability
from .strategy_ai_shadow_v2_hardening import install_ai_shadow_v2_hardening
from .strategy_ai_shadow_v2_catalyst_provenance import (
    install_ai_shadow_v2_catalyst_consistency,
    install_ai_shadow_v2_catalyst_provenance,
)
from .strategy_ai_shadow_v2_roadmap_policy import install_ai_shadow_v2_roadmap_policy
from .strategy_ai_shadow_v2_schedule_policy import install_ai_shadow_v2_schedule_policy
from .strategy_ai_shadow_v2_metrics_policy import install_ai_shadow_v2_metrics_policy
from .strategy_ai_shadow_v2_risk_policy import install_ai_shadow_v2_risk_policy
from .strategy_runtime_reliability_fixes import install_strategy_runtime_reliability_fixes
from .strategy_shadow_data_gap_guard import install_shadow_data_gap_guard
from .strategy_intraday_llm_reliability import install_intraday_llm_reliability
from .strategy_ai_shadow_v2_circuit_guard import install_ai_shadow_v2_circuit_guard

# Reliability installs first so the market-data layer wraps the final AI provider
# behavior rather than bypassing its retry/structured-output/circuit protections.
install_ai_shadow_reliability()
install_persistent_ai_shadow_circuit()
install_trading_data_hardening()
install_trading_data_runtime_refinements()
install_trading_session_reliability()
install_ai_shadow_v2_hardening()
install_ai_shadow_v2_catalyst_provenance()
install_ai_shadow_v2_roadmap_policy()
install_ai_shadow_v2_catalyst_consistency()
install_ai_shadow_v2_schedule_policy()
install_ai_shadow_v2_metrics_policy()
install_ai_shadow_v2_risk_policy()
# Install last: these layers must wrap the final stacked monitor/policy methods.
install_strategy_runtime_reliability_fixes()
install_shadow_data_gap_guard()
install_intraday_llm_reliability()
install_ai_shadow_v2_circuit_guard()

__all__ = [
    "CanonicalInstrument",
    "DatasetProvenance",
    "MarketBar",
    "ProviderBinding",
    "ProviderPolicy",
]
