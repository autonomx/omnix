from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from copy import deepcopy
from functools import wraps
from types import ModuleType
from typing import Any, Mapping

from app.rpg.session.turn_memory_contract import attach_turn_memory_context_with_session

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_POST_IMPORT_FINDER_ATTR = "_phase1433_turn_memory_runtime_finder_installed"
_PATCH_ATTR = "_phase1433_turn_memory_runtime_hook_installed"
_ORIGINAL_APPLY_TURN_ATTR = "_phase1433_original_interactive_apply_turn"


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _extract_call_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": _s(kwargs.get("session_id") if "session_id" in kwargs else (args[0] if len(args) >= 1 else "")),
        "player_input": _s(kwargs.get("player_input") if "player_input" in kwargs else (args[1] if len(args) >= 2 else "")),
        "session_override": deepcopy(_d(kwargs.get("session_override"))),
    }


def _load_persisted_session(session_id: str) -> dict[str, Any]:
    if not session_id:
        return {}
    try:
        from app.rpg.session import runtime as canonical_runtime

        return _d(canonical_runtime.load_runtime_session(session_id))
    except Exception:
        return {}


def _save_persisted_session(session: Mapping[str, Any], *, session_id: str) -> bool:
    if not session_id or not isinstance(session, Mapping):
        return False
    try:
        from app.rpg.session import runtime as canonical_runtime

        session_to_save = deepcopy(_d(session))
        manifest = _d(session_to_save.get("manifest"))
        manifest.setdefault("session_id", session_id)
        manifest.setdefault("id", session_id)
        session_to_save["manifest"] = manifest
        canonical_runtime.save_runtime_session(session_to_save)
        return True
    except Exception:
        return False


def _select_memory_session(result: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    session_id = _s(context.get("session_id"))
    persisted = _load_persisted_session(session_id)
    if persisted:
        return persisted, True
    result_session = _d(_d(result).get("session"))
    if result_session:
        return result_session, False
    override = _d(context.get("session_override"))
    if override:
        return override, False
    return {}, False


def attach_turn_memory_to_runtime_result(result: dict[str, Any], *, call_context: Mapping[str, Any]) -> dict[str, Any]:
    """Attach deterministic recent/dialogue memory to an interactive turn result."""

    if not isinstance(result, dict):
        return result
    context = _d(call_context)
    try:
        session, can_persist = _select_memory_session(result, context)
        updated_result, updated_session = attach_turn_memory_context_with_session(
            result,
            session=session,
            player_input=_s(context.get("player_input")),
        )
        persisted = _save_persisted_session(updated_session, session_id=_s(context.get("session_id"))) if can_persist else False
        hook_status = {
            "format_version": "phase14_33_turn_memory_runtime_hook_v1",
            "attached": True,
            "persisted": persisted,
            "state_path": "runtime_state.turn_memory",
            "deterministic": True,
            "presentation_only": True,
        }
        updated_result["turn_memory_runtime_hook"] = hook_status
        nested = _d(updated_result.get("result"))
        if nested:
            nested["turn_memory_runtime_hook"] = dict(hook_status)
            updated_result["result"] = nested
        return updated_result
    except Exception as exc:
        result["turn_memory_runtime_hook"] = {
            "format_version": "phase14_33_turn_memory_runtime_hook_v1",
            "attached": False,
            "error": f"{type(exc).__name__}: {exc}",
            "deterministic": True,
            "presentation_only": True,
        }
        return result


def _patch_interactive_module(module: ModuleType) -> bool:
    if getattr(module, _PATCH_ATTR, False):
        return False
    original = getattr(module, "apply_turn", None)
    if not callable(original):
        return False

    @wraps(original)
    def _wrapped_apply_turn(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if isinstance(result, dict):
            return attach_turn_memory_to_runtime_result(result, call_context=_extract_call_context(args, kwargs))
        return result

    _wrapped_apply_turn.__module__ = getattr(original, "__module__", _INTERACTIVE_MODULE)
    _wrapped_apply_turn.__name__ = getattr(original, "__name__", "apply_turn")
    _wrapped_apply_turn.__qualname__ = getattr(original, "__qualname__", "apply_turn")

    setattr(module, _ORIGINAL_APPLY_TURN_ATTR, original)
    setattr(module, "apply_turn", _wrapped_apply_turn)
    setattr(module, _PATCH_ATTR, True)
    return True


def _preserve_player_agency_hook(module: ModuleType) -> None:
    try:
        from app.rpg.session.player_agency_runtime_hook import force_install_player_agency_runtime_hook_for_tests

        force_install_player_agency_runtime_hook_for_tests(module)
    except Exception:
        return


class _InteractivePostImportLoader(importlib.abc.Loader):
    def __init__(self, wrapped_loader: importlib.abc.Loader):
        self._wrapped_loader = wrapped_loader

    def create_module(self, spec):  # type: ignore[no-untyped-def]
        create_module = getattr(self._wrapped_loader, "create_module", None)
        if callable(create_module):
            return create_module(spec)
        return None

    def exec_module(self, module):  # type: ignore[no-untyped-def]
        self._wrapped_loader.exec_module(module)  # type: ignore[attr-defined]
        if module.__name__ == _INTERACTIVE_MODULE:
            _preserve_player_agency_hook(module)
            _patch_interactive_module(module)


class _InteractivePostImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname != _INTERACTIVE_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or isinstance(spec.loader, _InteractivePostImportLoader):
            return spec
        spec.loader = _InteractivePostImportLoader(spec.loader)
        return spec


def _install_post_import_finder() -> bool:
    if getattr(sys, _POST_IMPORT_FINDER_ATTR, False):
        return False
    sys.meta_path.insert(0, _InteractivePostImportFinder())
    setattr(sys, _POST_IMPORT_FINDER_ATTR, True)
    return True


def install_turn_memory_runtime_hook() -> bool:
    module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        _preserve_player_agency_hook(module)
        if _patch_interactive_module(module):
            return True
    return _install_post_import_finder()


def force_install_turn_memory_runtime_hook_for_tests(module: ModuleType | None = None) -> bool:
    if module is None:
        module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        original = getattr(module, _ORIGINAL_APPLY_TURN_ATTR, None)
        if callable(original):
            setattr(module, "apply_turn", original)
        if hasattr(module, _PATCH_ATTR):
            setattr(module, _PATCH_ATTR, False)
        return _patch_interactive_module(module)
    return install_turn_memory_runtime_hook()
