"""Which provider and model trading's research calls use: the "Trading model" setting, or the default provider.

Settings store it as a task-routing override under ``TRADING_ROUTE_KEY`` (``global.routing.taskOverrides``):
``{"providerId": ..., "modelId": ...}``, both optional. No provider means the default LLM provider; no model means that
provider's configured model. Research only: which model answers grants nothing, and execution stays deterministic.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

from app.providers.catalog import LOADED_MODEL, LOCAL_DEVICE, THINKING_OFF, provider_supports

logger = logging.getLogger(__name__)

TRADING_ROUTE_KEY = "trading-research"
# A real day's catalyst prompt reached 21,041 tokens, before the reply.
MIN_LOCAL_CONTEXT_TOKENS = 32_000
LOCAL_OUTPUT_MULTIPLIER = 2
# Live batches reached 14 stocks and 26,000 prompt tokens, past the 30-45 s deadlines.
LOCAL_BATCH_STOCKS = 5
LOCAL_LANE_WAIT_SECONDS = 60.0
LOCAL_MODEL_LANE = threading.RLock()
T = TypeVar("T")


class _LoadedModelProvider(Protocol):
    """A provider that supports ``LOADED_MODEL`` (LM Studio): it says what it has loaded."""

    def loaded_model_key(self) -> str | None: ...

    def loaded_model(self) -> tuple[str, int | None] | None: ...


class TradingLocalLaneBusy(RuntimeError):
    """Another local model call held the lane for the whole wait; this one was not sent."""


class TradingLocalModelNotReady(RuntimeError):
    """The pinned local model is not the one loaded; no request was sent."""


@dataclass(frozen=True)
class TradingModel:
    provider_id: str | None = None  # None: the default LLM provider
    model_id: str | None = None  # None: that provider's configured model


@dataclass(frozen=True)
class LocalModelReadiness:
    applicable: bool  # False: trading is not on a provider that keeps a model loaded
    ready: bool
    model: str | None = None
    context_length: int | None = None
    problems: tuple[str, ...] = ()


def trading_model() -> TradingModel:
    """The Trading model setting; the default provider when it is unset or cannot be read."""
    try:
        from app.providers.model_route import task_override_route
        from app.settings.effective_defaults import load_effective_profile

        route = task_override_route(load_effective_profile(), TRADING_ROUTE_KEY)
    except Exception:  # noqa: BLE001 - research keeps working on the default provider
        logger.warning("trading_model_setting_unreadable", exc_info=True)
        return TradingModel()
    return TradingModel(route.provider or None, route.model or None)


def trading_provider(default_lookup: Callable[[], Any] | None = None) -> Any:
    """The provider the Trading model setting names; unset, ``default_lookup`` (the default provider).

    A provider chosen without a model follows what it has loaded, so loading another model in LM Studio moves trading
    to it, rather than a stale configured model being loaded over it.
    """
    from app.providers import service as provider_service

    chosen = trading_model()
    if chosen.provider_id is None and chosen.model_id is None:
        return (default_lookup or provider_service.get_provider)()
    provider = provider_service.get_routed_provider(chosen.provider_id, chosen.model_id)
    if provider is None or not provider_supports(provider, LOADED_MODEL):
        return provider
    loaded = cast(_LoadedModelProvider, provider).loaded_model_key()
    if chosen.model_id is None:
        return provider_service.get_routed_provider(chosen.provider_id, loaded) if loaded else provider
    if loaded != chosen.model_id:
        # Asking for another model makes LM Studio load it, at a default context, over what the person loaded.
        raise TradingLocalModelNotReady(f"pinned={chosen.model_id};loaded={loaded}")
    return provider


def local_model_readiness() -> LocalModelReadiness:
    """Whether the local model trading will use is loaded, the pinned one, and large enough for its prompts."""
    from app.providers import service as provider_service

    chosen = trading_model()
    provider = (
        provider_service.get_routed_provider(chosen.provider_id, chosen.model_id)
        if chosen.provider_id is not None or chosen.model_id is not None
        else provider_service.get_provider()
    )
    if provider is None or not provider_supports(provider, LOADED_MODEL):
        return LocalModelReadiness(applicable=False, ready=True)
    loaded = cast(_LoadedModelProvider, provider).loaded_model()
    if loaded is None:
        return LocalModelReadiness(applicable=True, ready=False, problems=("NO_MODEL_LOADED",))
    model, context = loaded
    problems: list[str] = []
    if chosen.model_id is not None and model != chosen.model_id:
        problems.append("WRONG_MODEL_LOADED")
    if context is not None and context < MIN_LOCAL_CONTEXT_TOKENS:
        problems.append("CONTEXT_TOO_SMALL")
    return LocalModelReadiness(applicable=True, ready=not problems, model=model, context_length=context, problems=tuple(problems))


def is_local_provider(provider: Any) -> bool:
    return provider_supports(provider, LOCAL_DEVICE)


def local_output_limit(provider: Any, max_tokens: int) -> int:
    """A local model's output costs no quota, and its answers ran past limits sized for a hosted model's."""
    return max_tokens * LOCAL_OUTPUT_MULTIPLIER if is_local_provider(provider) else max_tokens


@contextmanager
def local_model_lane(provider: Any) -> Iterator[None]:
    """One local model call at a time: concurrent calls on one GPU ran past every deadline on 2026-11-09."""
    if not is_local_provider(provider):
        yield
        return
    if not LOCAL_MODEL_LANE.acquire(timeout=LOCAL_LANE_WAIT_SECONDS):
        raise TradingLocalLaneBusy(f"waited_seconds={LOCAL_LANE_WAIT_SECONDS:.0f}")
    try:
        yield
    finally:
        LOCAL_MODEL_LANE.release()


def local_batch_rows(rows: Sequence[T], *, is_open: Callable[[T], bool]) -> list[T]:
    """On a local model, what a call may cover: stocks with something open first, then the best-ranked, up to the cap."""
    if not trading_provider_is_local():
        return list(rows)
    open_rows = [row for row in rows if is_open(row)]
    held = {id(row) for row in open_rows}
    return (open_rows + [row for row in rows if id(row) not in held])[:LOCAL_BATCH_STOCKS]


def trading_provider_is_local() -> bool:
    """Whether trading's calls run on this machine, so they spend no provider quota.

    Asked by the budget on every call, so it reads ids and never asks the provider what it has loaded.
    """
    try:
        from app.providers import service as provider_service

        return provider_supports(trading_model().provider_id or provider_service.get_provider(), LOCAL_DEVICE)
    except Exception:  # noqa: BLE001 - when unsure, the daily budget stays on
        logger.warning("trading_provider_locality_unknown", exc_info=True)
        return False


def no_thinking_options(provider: Any) -> dict[str, bool]:
    """Call options that stop a local model thinking first.

    Trading's output limits and 30-60 s deadlines are sized for an answer, not for a reasoning trace: on LM Studio,
    Qwen 3.8 27B spent the whole limit thinking and never answered. Hosted models keep their own behaviour.
    """
    if provider_supports(provider, LOCAL_DEVICE) and provider_supports(provider, THINKING_OFF):
        return {"thinking": False}
    return {}


__all__ = [
    "LOCAL_BATCH_STOCKS",
    "LOCAL_MODEL_LANE",
    "LOCAL_OUTPUT_MULTIPLIER",
    "TradingLocalLaneBusy",
    "local_batch_rows",
    "local_model_lane",
    "LocalModelReadiness",
    "MIN_LOCAL_CONTEXT_TOKENS",
    "TRADING_ROUTE_KEY",
    "TradingLocalModelNotReady",
    "TradingModel",
    "is_local_provider",
    "local_model_readiness",
    "local_output_limit",
    "no_thinking_options",
    "trading_model",
    "trading_provider",
    "trading_provider_is_local",
]
