"""The one helper both save paths call before ``_commit_chat_reply`` (GUI-1.4).

It runs the resolvers (binding scope, market-symbol validation), compiles the
reply and returns what to merge into the reply's metadata: ``{"ui": payload}``,
``{"ui_error": ...}`` when compiling failed, or ``{}`` for a reply without an
``omnix-ui`` fence. It never raises: a reply is never lost because of its UI.
It must be called before the commit lock is taken, since resolvers do I/O.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from .bindings import DEFAULT_SYMBOL_TIMEOUT_SECONDS, binding_sources, requested_market_symbols, resolve_market_symbols
from .compiler import CompileScope, compile_chat_ui, has_ui_fence, utc_now

logger = logging.getLogger(__name__)


def reply_is_interrupted(metadata: Mapping[str, Any]) -> bool:
    return metadata.get("delivery_status") == "interrupted" or metadata.get("generation_status") == "interrupted"


def finalize_reply_ui(
    content: str,
    metadata: Mapping[str, Any] | None = None,
    *,
    context_items: Sequence[Mapping[str, Any]] | None = None,
    symbol_lookup: Any = None,
    symbol_timeout_seconds: float | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Metadata additions for a finished reply; ``{}`` when it has no ```omnix-ui fence."""
    reply_metadata = metadata or {}
    # Memory commands answer with deterministic text; interrupted replies get no UI (invariant 9).
    if reply_metadata.get("memory_command") or reply_is_interrupted(reply_metadata):
        return {}
    try:
        if not has_ui_fence(content):
            return {}
        symbols = requested_market_symbols(content)
        timeout = DEFAULT_SYMBOL_TIMEOUT_SECONDS if symbol_timeout_seconds is None else min(
            DEFAULT_SYMBOL_TIMEOUT_SECONDS, max(0.0, symbol_timeout_seconds),
        )
        scope = CompileScope(
            sources=binding_sources(context_items),
            market_symbols=resolve_market_symbols(symbols, lookup=symbol_lookup, timeout_seconds=timeout),
            clock=clock if clock is not None else utc_now,
        )
        payload = compile_chat_ui(content, scope)
    except Exception as exc:
        logger.warning("chat_ui_compile_failed", exc_info=True)
        return {"ui_error": {"code": "compile_failed", "error_type": type(exc).__name__}}
    return {"ui": payload} if payload is not None else {}


def attach_reply_ui(
    content: str,
    metadata: dict[str, Any],
    *,
    context_items: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    """Compile a finished reply into ``metadata`` (``ui`` or ``ui_error``) and record its block metrics.

    The save paths call this before ``_commit_chat_reply``; it never raises.
    """
    additions = finalize_reply_ui(content, metadata, context_items=context_items)
    if not additions:
        return
    metadata.update(additions)
    try:
        from ..provider_metrics import record_ui_metrics

        record_ui_metrics(metadata)
    except Exception:
        logger.warning("chat_ui_metrics_failed", exc_info=True)
