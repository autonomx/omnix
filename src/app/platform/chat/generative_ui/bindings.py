"""Binding scope and resolvers that run before a reply is committed (GUI-4).

``binding_sources`` builds the turn's bindable data from what the turn already
has: its context items, numbered as the prompt numbers them (``context:<n>``),
and research citations (``source:<n>`` is the source cited as ``[S<n>]``).
There are no tool bindings: assistant tools record only summary text.

``resolve_market_symbols`` checks ``price_chart`` symbols against trading's
read-only instrument catalog through chat's ``CHAT_MARKET_SYMBOLS`` port, with
a time limit. A symbol that cannot be checked in time is left out, so its block
degrades to text instead of delaying the commit.
"""
from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from .catalog import SYMBOL, BoundSource
from .parser import parse_fence_json, scan_fences

logger = logging.getLogger(__name__)

_CITATION = re.compile(r"^S(\d{1,3})$", re.I)
_TITLE_CITATION_PREFIX = re.compile(r"^\[S\d{1,3}\]\s*", re.I)
DEFAULT_SYMBOL_TIMEOUT_SECONDS = 3.0


def binding_sources(context_items: Sequence[Mapping[str, Any]] | None) -> dict[str, BoundSource]:
    """``context:<n>`` for every context item and ``source:<n>`` for research citations."""
    sources: dict[str, BoundSource] = {}
    for index, item in enumerate(context_items or (), start=1):
        if not isinstance(item, Mapping):
            continue
        raw_metadata = item.get("metadata")
        metadata: Mapping[str, Any] = raw_metadata if isinstance(raw_metadata, Mapping) else {}
        citation = str(metadata.get("citation_label") or item.get("citation") or "").strip().upper() or None
        source_id = str(item.get("source_id") or "context").strip()
        title = _TITLE_CITATION_PREFIX.sub("", str(item.get("title") or "").strip()) or source_id
        url = str(item.get("url") or "").strip() or None
        sources[f"context:{index}"] = BoundSource(ref=f"context:{index}", title=title, url=url, citation=citation)
        match = _CITATION.match(citation or "")
        if match:
            ref = f"source:{int(match.group(1))}"
            sources.setdefault(ref, BoundSource(ref=ref, title=title, url=url, citation=citation))
    return sources


def requested_market_symbols(content: str) -> list[str]:
    """Symbols named by ``price_chart`` blocks, in order, without duplicates."""
    symbols: list[str] = []
    for fence in scan_fences(content):
        try:
            spec = parse_fence_json(fence.body).value
        except ValueError:
            continue
        if not isinstance(spec, dict) or spec.get("type") != "price_chart":
            continue
        raw = spec.get("symbol")
        symbol = raw.strip().upper() if isinstance(raw, str) else ""
        if SYMBOL.match(symbol) and symbol not in symbols:
            symbols.append(symbol)
    return symbols[:8]


def resolve_market_symbols(
    symbols: Sequence[str],
    *,
    lookup: Any = None,
    timeout_seconds: float = DEFAULT_SYMBOL_TIMEOUT_SECONDS,
) -> dict[str, str] | None:
    """Symbol -> instrument id for the symbols trading's catalog knows.

    None when the symbols could not be checked (no trading feature, a failed
    lookup, or the time limit passed); the blocks then show as unverified.
    """
    if not symbols:
        return {}
    if lookup is None:
        from app.runtime.ports import optional

        from ..contracts import CHAT_MARKET_SYMBOLS

        lookup = optional(CHAT_MARKET_SYMBOLS)
        if lookup is None:
            return None
    resolved: dict[str, str] = {}
    failed = threading.Event()
    done = threading.Event()

    def run() -> None:
        try:
            for symbol in symbols:
                instrument_id = lookup.instrument_id(symbol)
                if isinstance(instrument_id, str) and instrument_id:
                    resolved[symbol] = instrument_id
        except Exception:
            logger.warning("chat_ui_symbol_lookup_failed", exc_info=True)
            failed.set()
        finally:
            done.set()

    # A daemon thread: a stalled provider cannot hold the reply past the limit.
    threading.Thread(target=run, name="omnix-chat-ui-symbols", daemon=True).start()
    if not done.wait(max(0.0, timeout_seconds)):
        logger.warning("chat_ui_symbol_lookup_timed_out symbols=%s", list(symbols))
        return None
    return None if failed.is_set() else dict(resolved)
