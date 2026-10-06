"""The RPG's tolerant readers of loosely typed state (WP-8.6).

One definition for the coercions RPG modules used to copy locally. Each keeps
the exact behaviour of the copies it replaces: ``safe_dict`` and ``safe_list``
return the value itself; ``dict_copy``, ``list_copy`` and ``mapping_copy`` a shallow copy.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def safe_dict(value: Any) -> dict[str, Any]:
    """The value if it is a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def dict_copy(value: Any) -> dict[str, Any]:
    """A shallow copy of the value if it is a dict, else an empty dict."""
    return dict(value) if isinstance(value, dict) else {}


def safe_list(value: Any) -> list[Any]:
    """The value if it is a list, else an empty list."""
    return value if isinstance(value, list) else []


def list_copy(value: Any) -> list[Any]:
    """A shallow copy of the value if it is a list, else an empty list."""
    return list(value) if isinstance(value, list) else []


def safe_str(value: Any) -> str:
    """``''`` for None, else ``str(value)``."""
    return "" if value is None else str(value)


def mapping_copy(value: Any) -> dict[str, Any]:
    """A plain dict copy of the value if it is any Mapping, else an empty dict."""
    return dict(value) if isinstance(value, Mapping) else {}
