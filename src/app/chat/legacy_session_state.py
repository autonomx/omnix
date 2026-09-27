"""Legacy session callback bridge retained only for compatibility tests/importers."""
from __future__ import annotations

from threading import RLock
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")
_lock = RLock()
_load: Callable[[], dict[str, Any]] | None = None
_save: Callable[[dict[str, Any]], None] | None = None
_update: Callable[[Callable[[dict[str, Any]], _T]], tuple[dict[str, Any], _T]] | None = None
_sessions: dict[str, Any] = {}


def install_legacy_session_callbacks(
    *,
    load_callback: Callable[[], dict[str, Any]],
    save_callback: Callable[[dict[str, Any]], None],
    update_callback: Callable[[Callable[[dict[str, Any]], _T]], tuple[dict[str, Any], _T]] | None = None,
) -> None:
    global _load, _save, _update
    with _lock:
        _load = load_callback
        _save = save_callback
        _update = update_callback


def clear_legacy_session_callbacks() -> None:
    global _load, _save, _update, _sessions
    with _lock:
        _load = None
        _save = None
        _update = None
        _sessions = {}


def load_sessions() -> dict[str, Any]:
    with _lock:
        loader = _load
        if loader is None:
            return dict(_sessions)
    return dict(loader() or {})


def save_sessions(sessions: dict[str, Any]) -> None:
    global _sessions
    payload = dict(sessions or {})
    with _lock:
        saver = _save
        if saver is None:
            _sessions = payload
            return
    saver(payload)


def update_sessions(mutator: Callable[[dict[str, Any]], _T]) -> _T:
    global _sessions
    with _lock:
        updater = _update
        if updater is not None:
            current, result = updater(mutator)
            _sessions = dict(current or {})
            return result
        current = load_sessions()
        result = mutator(current)
        save_sessions(current)
        _sessions = dict(current)
        return result
