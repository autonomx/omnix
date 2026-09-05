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

# Keep the AI research arm isolated and fail-closed without changing deterministic
# trading authority or AUTO PAPER execution paths.
install_ai_shadow_reliability()
install_persistent_ai_shadow_circuit()

__all__ = [
    "CanonicalInstrument",
    "DatasetProvenance",
    "MarketBar",
    "ProviderBinding",
    "ProviderPolicy",
]