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
from .strategy_runtime_compatibility_fixes import install_strategy_runtime_compatibility_fixes
from .strategy_dynamic_discovery_completeness import (
    install_dynamic_discovery_completeness,
)
from .strategy_dynamic_discovery_completeness_refinements import (
    install_dynamic_discovery_completeness_refinements,
)

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

# Session/runtime overlays intentionally install after the complete V2 policy
# stack so their saved originals point at the final causal/metrics behavior.
install_strategy_runtime_reliability_fixes()
install_shadow_data_gap_guard()
install_intraday_llm_reliability()
install_ai_shadow_v2_circuit_guard()
install_strategy_runtime_compatibility_fixes()

# Causal-discovery completeness installs last so live discovery, replay, learning,
# attribution, and SHADOW-universe consumers share one state-transition authority.
install_dynamic_discovery_completeness()
install_dynamic_discovery_completeness_refinements()

__all__ = [
    "CanonicalInstrument",
    "DatasetProvenance",
    "MarketBar",
    "ProviderBinding",
    "ProviderPolicy",
]
