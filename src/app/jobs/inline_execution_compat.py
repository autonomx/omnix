"""Compatibility marker for jobs executed locally without a queue worker."""

from __future__ import annotations

from typing import Any


def mark_inline_execution(request: Any) -> Any:
    """Return a request whose persisted compatibility contract permits local execution."""
    compat = dict(getattr(request, "compat", None) or {})
    compat["inline_execution"] = True
    model_copy = getattr(request, "model_copy", None)
    if callable(model_copy):
        return model_copy(update={"compat": compat})
    setattr(request, "compat", compat)
    return request
