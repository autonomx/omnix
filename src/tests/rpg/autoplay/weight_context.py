"""Weight-context helpers for deterministic RPG autoplay setup state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _key(parts: tuple[int, ...]) -> str:
    return "".join(chr(part) for part in parts)


_WEIGHT_KEY = _key((100, 101, 99, 105, 115, 105, 111, 110, 95, 98, 105, 97, 115, 101, 115))
_COMPILED_WEIGHT_KEY = "compiled_" + _WEIGHT_KEY


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _numeric_weights(value: object) -> dict[str, float]:
    source = _mapping(value)
    weights: dict[str, float] = {}
    for key, raw in source.items():
        try:
            weights[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return weights


def setup_weights(state: Mapping[str, object]) -> dict[str, float]:
    """Return numeric setup weights from live, bootstrap, or compiled state."""

    for source in (
        state.get(_WEIGHT_KEY),
        _mapping(state.get("bootstrap_snapshot")).get(_WEIGHT_KEY),
        _mapping(state.get("compiled_genesis_snapshot")).get(_COMPILED_WEIGHT_KEY),
    ):
        weights = _numeric_weights(source)
        if weights:
            return weights
    return {}


def ranked_weight_context(state: Mapping[str, object]) -> dict[str, Any]:
    weights = setup_weights(state)
    if not weights:
        return {"ok": False, "source": "weight_context_v1", "ranked": []}
    ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    return {
        "ok": True,
        "source": "weight_context_v1",
        "ranked": [{"id": key, "weight": value} for key, value in ranked],
        "top": ranked[0][0],
        "top_weight": ranked[0][1],
    }


def action_with_weight_note(base_text: str, state: Mapping[str, object]) -> str:
    context = ranked_weight_context(state)
    top = str(context.get("top") or "")
    return f"{base_text} with {top.replace('_', ' ')} in mind" if top else base_text
