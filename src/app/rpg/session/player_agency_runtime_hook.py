from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys
from functools import wraps
from types import ModuleType
from typing import Any, Mapping

from app.rpg.session.player_agency_contract import attach_player_agency_contract

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_POST_IMPORT_FINDER_ATTR = "_phase1420_player_agency_runtime_finder_installed"
_PATCH_ATTR = "_phase1420_player_agency_runtime_hook_installed"
_ORIGINAL_APPLY_TURN_ATTR = "_phase1420_original_interactive_apply_turn"


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _b(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"1", "true", "yes", "y", "on"}:
            return True
        if lower in {"0", "false", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _extract_call_context(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    performance_override = _d(kwargs.get("performance_override"))
    session_override = _d(kwargs.get("session_override"))
    return {
        "session_id": _s(kwargs.get("session_id") if "session_id" in kwargs else (args[0] if len(args) >= 1 else "")),
        "player_input": _s(kwargs.get("player_input") if "player_input" in kwargs else (args[1] if len(args) >= 2 else "")),
        "performance_override": performance_override,
        "session_override": session_override,
        "max_options": int(performance_override.get("player_agency_max_options") or 5),
        "enable_flavor": _b(performance_override.get("enable_player_agency_flavor"), False),
    }


def _optional_flavor_provider(enable_flavor: bool) -> Any:
    if not enable_flavor:
        return None
    try:
        from app.rpg.llm_app_gateway import build_app_llm_gateway

        return build_app_llm_gateway()
    except Exception:
        return None


def attach_player_agency_to_runtime_result(result: dict[str, Any], *, call_context: Mapping[str, Any]) -> dict[str, Any]:
    """Attach the Phase 14.19 next-action contract to a runtime turn result.

    This is presentation/affordance metadata only. Commands remain suggestions and
    must be sent back through normal runtime validation if clicked or typed.
    """

    if not isinstance(result, dict):
        return result
    context = _d(call_context)
    provider = _optional_flavor_provider(_b(context.get("enable_flavor"), False))
    try:
        updated = attach_player_agency_contract(
            result,
            player_input=_s(context.get("player_input")),
            session=_d(context.get("session_override")),
            provider=provider,
            max_options=int(context.get("max_options") or 5),
        )
        updated["player_agency_runtime_hook"] = {
            "format_version": "phase14_20_player_agency_runtime_hook_v1",
            "attached": True,
            "provider_flavor_requested": _b(context.get("enable_flavor"), False),
            "provider_flavor_available": provider is not None,
            "presentation_only": True,
            "runtime_validation_required": True,
        }
        nested = _d(updated.get("result"))
        if nested:
            nested["player_agency_runtime_hook"] = dict(updated["player_agency_runtime_hook"])
            updated["result"] = nested
        return updated
    except Exception as exc:
        result["player_agency_runtime_hook"] = {
            "format_version": "phase14_20_player_agency_runtime_hook_v1",
            "attached": False,
            "error": f"{type(exc).__name__}: {exc}",
            "presentation_only": True,
            "runtime_validation_required": True,
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
            return attach_player_agency_to_runtime_result(result, call_context=_extract_call_context(args, kwargs))
        return result

    _wrapped_apply_turn.__module__ = getattr(original, "__module__", _INTERACTIVE_MODULE)
    _wrapped_apply_turn.__name__ = getattr(original, "__name__", "apply_turn")
    _wrapped_apply_turn.__qualname__ = getattr(original, "__qualname__", "apply_turn")

    setattr(module, _ORIGINAL_APPLY_TURN_ATTR, original)
    setattr(module, "apply_turn", _wrapped_apply_turn)
    setattr(module, _PATCH_ATTR, True)
    return True


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


def install_player_agency_runtime_hook() -> bool:
    module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType) and _patch_interactive_module(module):
        return True
    return _install_post_import_finder()


def force_install_player_agency_runtime_hook_for_tests(module: ModuleType | None = None) -> bool:
    if module is None:
        module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        original = getattr(module, _ORIGINAL_APPLY_TURN_ATTR, None)
        if callable(original):
            setattr(module, "apply_turn", original)
        if hasattr(module, _PATCH_ATTR):
            setattr(module, _PATCH_ATTR, False)
        return _patch_interactive_module(module)
    return install_player_agency_runtime_hook()
