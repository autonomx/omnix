from __future__ import annotations

"""Shared provider reliability for event-driven intraday LLM research.

Default intraday LLM calls use the same isolated provider instance, serialization
lock and durable outage circuit as AI Shadow. Injected providers used by tests or
special research remain untouched.
"""

from . import ai_shadow_reliability as reliability
from . import strategy_intraday_llm as intraday
from .trading_session_reliability import _IntradaySchemaProviderProxy

_INSTALLED = False
_ORIGINAL_ASSESS = None
_ORIGINAL_AI_SHADOW_CHAT_CALL = None


def _dedicated_intraday_provider():
    provider = reliability.get_trading_research_provider()
    if provider is None:
        return None
    provider_name = str(
        getattr(provider, "provider_name", "")
        or getattr(getattr(provider, "config", None), "provider_type", "")
    ).strip().casefold()
    return (
        _IntradaySchemaProviderProxy(provider)
        if provider_name == "chatgpt_codex"
        else provider
    )


def _reliable_intraday_assess(self, *args, **kwargs):
    assert _ORIGINAL_ASSESS is not None
    # Preserve explicitly injected fixtures/providers. Only the normal Omnix
    # default research lane participates in the shared provider circuit.
    if self.provider_factory is not intraday._default_provider:
        return _ORIGINAL_ASSESS(self, *args, **kwargs)

    with reliability._PROVIDER_LOCK:
        now = reliability.time.monotonic()
        circuit = reliability._CIRCUIT
        if circuit.is_open(now):
            raise reliability.AIShadowReliabilityError(
                "intraday_llm_provider_circuit_open",
                f"retry_after_seconds={circuit.retry_after(now)};failure_count={circuit.failure_count}",
            )
        original_factory = self.provider_factory
        self.provider_factory = _dedicated_intraday_provider
        try:
            result = _ORIGINAL_ASSESS(self, *args, **kwargs)
        except Exception as exc:
            if not reliability._transport_failure(exc):
                raise
            reliability._retire_trading_research_provider()
            delay = circuit.trip(reliability.time.monotonic())
            raise reliability.AIShadowReliabilityError(
                "intraday_llm_transport_exhausted",
                f"attempts=1;retry_after_seconds={delay};last={type(exc).__name__}:{exc}",
            ) from exc
        finally:
            self.provider_factory = original_factory
        circuit.success()
        return result


def _serialized_ai_shadow_chat_call(*args, **kwargs):
    assert _ORIGINAL_AI_SHADOW_CHAT_CALL is not None
    with reliability._PROVIDER_LOCK:
        return _ORIGINAL_AI_SHADOW_CHAT_CALL(*args, **kwargs)


def install_intraday_llm_reliability() -> None:
    global _INSTALLED, _ORIGINAL_ASSESS, _ORIGINAL_AI_SHADOW_CHAT_CALL
    if _INSTALLED:
        return
    _ORIGINAL_ASSESS = intraday.IntradayLLMAnalyzer.assess
    _ORIGINAL_AI_SHADOW_CHAT_CALL = reliability._chat_call
    intraday.IntradayLLMAnalyzer.assess = _reliable_intraday_assess
    # Legacy AI Shadow already owns retry/budget semantics; this wrapper only
    # serializes access to the shared long-lived provider process.
    reliability._chat_call = _serialized_ai_shadow_chat_call
    _INSTALLED = True


__all__ = ["install_intraday_llm_reliability"]
