"""Process-local serialization for Chat read-modify-write mutations."""
from __future__ import annotations

from functools import wraps
from threading import RLock
from typing import Any, Callable, TypeVar, cast

CHAT_MUTATION_LOCK = RLock()

_F = TypeVar("_F", bound=Callable[..., Any])


def serialized_chat_mutation(function: _F) -> _F:
    """Serialize a complete Chat mutation, including its load/save transaction."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with CHAT_MUTATION_LOCK:
            return function(*args, **kwargs)

    return cast(_F, wrapped)
