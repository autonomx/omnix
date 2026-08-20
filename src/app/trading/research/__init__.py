"""Causal trading research plus compatibility exports for legacy market research.

The repository historically exposed ``app.trading.research`` as a single module.
HTR introduces a package at that import path. Load the untouched sibling
``research.py`` under an internal module name so existing callers keep the exact
pre-HTR API and semantics while new causal research lives in package modules.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_legacy_path = Path(__file__).resolve().parent.parent / "research.py"
_legacy_name = "app.trading._legacy_market_research"
_spec = importlib.util.spec_from_file_location(_legacy_name, _legacy_path)
if _spec is None or _spec.loader is None:  # pragma: no cover - installation corruption
    raise ImportError(f"Unable to load legacy trading research module: {_legacy_path}")
_legacy = sys.modules.get(_legacy_name)
if _legacy is None:
    _legacy = importlib.util.module_from_spec(_spec)
    sys.modules[_legacy_name] = _legacy
    _spec.loader.exec_module(_legacy)

# Exact compatibility surface used by existing Trading research APIs/tests and
# catalyst_shadow. Keep these names stable until the legacy endpoint is retired.
MAX_RESEARCH_BARS = _legacy.MAX_RESEARCH_BARS
MAX_RESEARCH_PROMPT_CHARS = _legacy.MAX_RESEARCH_PROMPT_CHARS
MAX_RESEARCH_QUESTION_CHARS = _legacy.MAX_RESEARCH_QUESTION_CHARS
ResearchSource = _legacy.ResearchSource
MarketResearchRequest = _legacy.MarketResearchRequest
MarketResearchResult = _legacy.MarketResearchResult
ProviderLike = _legacy.ProviderLike
ProviderFactory = _legacy.ProviderFactory
MarketServiceFactory = _legacy.MarketServiceFactory
default_research_provider = _legacy.default_research_provider
build_research_context = _legacy.build_research_context
_provider_identity = _legacy._provider_identity
_provider_text = _legacy._provider_text
_call_provider = _legacy._call_provider
_json_payload = _legacy._json_payload
generate_market_research = _legacy.generate_market_research

from .contracts import (  # noqa: E402
    IssuerIdentity,
    StrategyResearchFeatures,
    TradingEvidence,
    TradingFactSet,
    TradingResearchReport,
    TradingResearchRequest,
)

__all__ = [
    "MAX_RESEARCH_BARS",
    "MAX_RESEARCH_PROMPT_CHARS",
    "MAX_RESEARCH_QUESTION_CHARS",
    "ResearchSource",
    "MarketResearchRequest",
    "MarketResearchResult",
    "ProviderLike",
    "ProviderFactory",
    "MarketServiceFactory",
    "default_research_provider",
    "build_research_context",
    "generate_market_research",
    "IssuerIdentity",
    "StrategyResearchFeatures",
    "TradingEvidence",
    "TradingFactSet",
    "TradingResearchReport",
    "TradingResearchRequest",
]
