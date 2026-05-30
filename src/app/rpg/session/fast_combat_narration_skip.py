from __future__ import annotations

import contextvars
import importlib.abc
import importlib.machinery
import sys
from types import ModuleType
from typing import Any, Dict

_FAST_DIRECT_SOURCES = {
    "ce211_fast_direct_runtime_budget_v1",
    "ce212_fast_direct_runtime_budget_v1",
}
_RUNTIME_MODULE = "app.rpg.session.runtime"
_POST_IMPORT_FINDER_ATTR = "_ce212_fast_combat_post_import_finder_installed"
_PATCH_ATTR = "_ce212_fast_combat_narration_skip_installed"
_ORIGINAL_ATTR = "_ce212_original_apply_combat_narration_if_needed"
_ORIGINAL_APPLY_TURN_ATTR = "_ce212_original_apply_turn_for_fast_combat_skip"
_FAST_COMBAT_SKIP_CONTEXT: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ce212_fast_combat_skip_context",
    default=False,
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _first_present_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except Exception:
                continue
    return None


def _contains_fast_direct_marker(value: Any, *, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(value, dict):
        source = _safe_str(value.get("source") or value.get("fast_direct_source"))
        if source in _FAST_DIRECT_SOURCES:
            return True
        if value.get("fast_direct_runtime") is True or value.get("skip_sync_combat_narration") is True:
            return True
        metadata = value.get("metadata")
        if isinstance(metadata, dict) and _contains_fast_direct_marker(metadata, depth=depth + 1):
            return True
        for key in (
            "turn_contract",
            "action",
            "first_call_action_advisory",
            "first_call_grounding_diagnostics",
            "turn_grounding_packet",
            "fast_direct_action",
            "semantic_action",
        ):
            if key in value and _contains_fast_direct_marker(value.get(key), depth=depth + 1):
                return True
    elif isinstance(value, list):
        return any(_contains_fast_direct_marker(item, depth=depth + 1) for item in value[:20])
    return False


def _is_combat_action(action: Dict[str, Any]) -> bool:
    action_type = _safe_str(action.get("action_type") or action.get("type")).strip().lower()
    if action_type == "combat":
        return True
    target = _safe_str(action.get("target_id") or action.get("target_name")).strip().lower()
    requested = " ".join(_safe_str(term).lower() for term in action.get("requested_terms") or [])
    return "bandit" in target and "attack" in requested


def _action_requests_fast_combat_skip(action: Any, performance_override: Any = None) -> bool:
    action_dict = _safe_dict(action)
    performance = _safe_dict(performance_override)
    if performance.get("skip_sync_combat_narration") is True or performance.get("fast_direct_runtime") is True:
        return True
    if _contains_fast_direct_marker(action_dict):
        return True
    return _safe_bool(performance.get("fast_turn_mode")) and _is_combat_action(action_dict)


def _should_skip(payload: Dict[str, Any], combat_state: Dict[str, Any]) -> bool:
    if _FAST_COMBAT_SKIP_CONTEXT.get(False):
        return True
    payload = _safe_dict(payload)
    combat_state = _safe_dict(combat_state)
    if payload.get("skip_sync_combat_narration") or payload.get("fast_direct_runtime"):
        return True
    if combat_state.get("skip_sync_combat_narration") or combat_state.get("fast_direct_runtime"):
        return True
    if _safe_str(payload.get("fast_direct_source")) in _FAST_DIRECT_SOURCES:
        return True
    if _safe_str(combat_state.get("fast_direct_source")) in _FAST_DIRECT_SOURCES:
        return True
    return _contains_fast_direct_marker(payload) or _contains_fast_direct_marker(combat_state)


def _combat_delta_contract(combat_result: Dict[str, Any], combat_state: Dict[str, Any]) -> Dict[str, Any]:
    combat_result = _safe_dict(combat_result)
    combat_state = _safe_dict(combat_state)
    delta = {
        "source": "deterministic_combat_delta_contract_v1",
        "action_type": _safe_str(combat_result.get("action_type") or combat_result.get("action")),
        "reason": _safe_str(combat_result.get("reason") or combat_result.get("result") or combat_result.get("outcome")),
        "actor_id": _safe_str(combat_result.get("actor_id") or combat_result.get("attacker_id") or combat_state.get("actor_id")),
        "target_id": _safe_str(combat_result.get("target_id") or combat_result.get("defender_id") or combat_state.get("target_id")),
        "target_name": _safe_str(combat_result.get("target_name") or combat_state.get("target_name") or "bandit"),
        "damage_applied": _first_present_int(
            combat_result.get("damage_applied"),
            combat_result.get("damage"),
            combat_result.get("damage_dealt"),
            combat_state.get("last_damage"),
        ),
        "target_hp_before": _first_present_int(
            combat_result.get("target_hp_before"),
            combat_result.get("enemy_hp_before"),
            combat_state.get("target_hp_before"),
            combat_state.get("enemy_hp_before"),
        ),
        "target_hp_after": _first_present_int(
            combat_result.get("target_hp_after"),
            combat_result.get("enemy_hp_after"),
            combat_result.get("enemy_hp"),
            combat_state.get("target_hp_after"),
            combat_state.get("enemy_hp_after"),
            combat_state.get("enemy_hp"),
        ),
        "defeated": bool(
            combat_result.get("defeated")
            or combat_result.get("enemy_defeated")
            or combat_result.get("combat_ended")
            or combat_state.get("defeated")
            or combat_state.get("enemy_defeated")
        ),
        "combat_ended": bool(
            combat_result.get("combat_ended")
            or combat_result.get("ended")
            or combat_state.get("combat_ended")
            or combat_state.get("ended")
        ),
    }
    return {key: value for key, value in delta.items() if value not in (None, "")}


def _fallback_summary(combat_result: Dict[str, Any], combat_state: Dict[str, Any] | None = None) -> str:
    combat_result = _safe_dict(combat_result)
    combat_state = _safe_dict(combat_state)
    delta = _combat_delta_contract(combat_result, combat_state)
    target_name = _safe_str(delta.get("target_name") or "enemy").strip() or "enemy"
    damage = delta.get("damage_applied")
    hp_after = delta.get("target_hp_after")
    defeated = bool(delta.get("defeated") or delta.get("combat_ended"))

    if isinstance(damage, int) and damage > 0:
        if defeated:
            return f"You hit the {target_name} for {damage} damage and defeat them."
        if isinstance(hp_after, int):
            return f"You hit the {target_name} for {damage} damage. The {target_name} has {hp_after} HP remaining."
        return f"You hit the {target_name} for {damage} damage."
    if defeated:
        return f"You defeat the {target_name}."
    for key in ("summary", "result", "outcome", "reason", "action_type"):
        text = _safe_str(combat_result.get(key)).strip()
        if text:
            return f"Result: {text}"
    return "Result: combat_action_resolved"


def _build_contract(runtime_module: Any, combat_result: Dict[str, Any], combat_state: Dict[str, Any]) -> Dict[str, Any]:
    builder = getattr(runtime_module, "build_combat_narration_contract", None)
    if callable(builder):
        try:
            return _safe_dict(builder(combat_result=combat_result, combat_state=combat_state))
        except Exception:
            return {}
    return {}


def _deterministic_payload(narration: str, combat_delta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "source": "deterministic_combat_fast_summary",
        "narration": narration,
        "npc": {},
        "combat_delta": _safe_dict(combat_delta),
    }


def _stale_or_empty_fast_combat_text(value: Any) -> bool:
    text = _safe_str(value).strip().casefold()
    return not text or "no injury is resolved" in text or "no injury was resolved" in text


def _apply_fast_skip(
    runtime_module: Any,
    payload: Dict[str, Any],
    *,
    combat_result: Dict[str, Any],
    combat_state: Dict[str, Any],
) -> Dict[str, Any]:
    payload = _safe_dict(payload)
    combat_result = _safe_dict(combat_result)
    combat_state = _safe_dict(combat_state)
    combat_delta = _combat_delta_contract(combat_result, combat_state)
    narration = _fallback_summary(combat_result, combat_state)
    deterministic_payload = _deterministic_payload(narration, combat_delta)

    payload["combat_narration_attempted"] = False
    payload["combat_narration_skipped_for_fast_mode"] = True
    payload["combat_narration_skip_source"] = "ce212_fast_combat_narration_skip_v1"
    payload["combat_delta_contract"] = dict(combat_delta)
    payload["llm_called"] = False
    payload["llm_purpose"] = "deterministic_combat_fast_summary"
    payload["combat_narration_error"] = ""
    payload["combat_narration_contract"] = _build_contract(runtime_module, combat_result, combat_state)
    payload["combat_narration_validation"] = {
        "ok": False,
        "warnings": ["combat_narration_skipped_for_fast_mode"],
        "source": "ce212_fast_combat_narration_skip_v1",
    }
    payload["combat_narration_payload"] = dict(deterministic_payload)
    payload["narration_payload"] = dict(deterministic_payload)
    payload["structured_narration"] = dict(deterministic_payload)
    payload["combat_narration_accepted"] = False
    payload["combat_narration_rejected"] = False

    for key in ("narration", "final_narration", "narration_preview", "raw_payload_narration"):
        if _stale_or_empty_fast_combat_text(payload.get(key)):
            payload[key] = narration
    nested = _safe_dict(payload.get("result"))
    if nested:
        nested["combat_narration_skipped_for_fast_mode"] = True
        nested["combat_narration_skip_source"] = "ce212_fast_combat_narration_skip_v1"
        nested["combat_delta_contract"] = dict(combat_delta)
        nested["combat_narration_payload"] = dict(deterministic_payload)
        nested["narration_payload"] = dict(deterministic_payload)
        nested["structured_narration"] = dict(deterministic_payload)
        for key in ("narration", "final_narration", "narration_preview", "raw_payload_narration"):
            if _stale_or_empty_fast_combat_text(nested.get(key)):
                nested[key] = narration
        payload["result"] = nested
    return payload


def _with_fast_combat_flags(
    args: tuple[Any, ...],
    kwargs: Dict[str, Any],
    *,
    action: Any,
    performance_override: Any,
) -> tuple[tuple[Any, ...], Dict[str, Any]]:
    patched_kwargs = dict(kwargs)
    patched_performance = _safe_dict(performance_override)
    patched_performance["skip_sync_combat_narration"] = True
    patched_performance["fast_direct_runtime"] = True
    patched_kwargs["performance_override"] = patched_performance

    if isinstance(action, dict):
        patched_action = dict(action)
        metadata = _safe_dict(patched_action.get("metadata"))
        metadata["skip_sync_combat_narration"] = True
        metadata["fast_direct_runtime"] = True
        metadata.setdefault("source", "ce212_fast_direct_runtime_budget_v1")
        patched_action["metadata"] = metadata
        if "action" in patched_kwargs:
            patched_kwargs["action"] = patched_action
        elif len(args) >= 3:
            patched_args = list(args)
            patched_args[2] = patched_action
            args = tuple(patched_args)
        else:
            patched_kwargs["action"] = patched_action
    return args, patched_kwargs


def _patch_runtime_module(runtime_module: ModuleType) -> bool:
    if getattr(runtime_module, _PATCH_ATTR, False):
        return False

    original = getattr(runtime_module, "_apply_combat_narration_if_needed", None)
    original_apply_turn = getattr(runtime_module, "apply_turn", None)
    if not callable(original):
        return False

    def _wrapped_apply_combat_narration_if_needed(
        payload: Dict[str, Any],
        *,
        combat_result: Dict[str, Any],
        combat_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        if _should_skip(_safe_dict(payload), _safe_dict(combat_state)):
            return _apply_fast_skip(
                runtime_module,
                payload,
                combat_result=combat_result,
                combat_state=combat_state,
            )
        return original(payload, combat_result=combat_result, combat_state=combat_state)

    setattr(runtime_module, _ORIGINAL_ATTR, original)
    setattr(runtime_module, "_apply_combat_narration_if_needed", _wrapped_apply_combat_narration_if_needed)

    if callable(original_apply_turn):

        def _wrapped_apply_turn(*args: Any, **kwargs: Any) -> Any:
            action = kwargs.get("action")
            if action is None and len(args) >= 3:
                action = args[2]
            performance_override = kwargs.get("performance_override")
            should_skip = _action_requests_fast_combat_skip(action, performance_override)
            if not should_skip:
                return original_apply_turn(*args, **kwargs)
            patched_args, patched_kwargs = _with_fast_combat_flags(
                args,
                kwargs,
                action=action,
                performance_override=performance_override,
            )
            token = _FAST_COMBAT_SKIP_CONTEXT.set(True)
            try:
                return original_apply_turn(*patched_args, **patched_kwargs)
            finally:
                _FAST_COMBAT_SKIP_CONTEXT.reset(token)

        setattr(runtime_module, _ORIGINAL_APPLY_TURN_ATTR, original_apply_turn)
        setattr(runtime_module, "apply_turn", _wrapped_apply_turn)

    setattr(runtime_module, _PATCH_ATTR, True)
    return True


class _RuntimePostImportLoader(importlib.abc.Loader):
    def __init__(self, wrapped_loader: importlib.abc.Loader):
        self._wrapped_loader = wrapped_loader

    def create_module(self, spec):  # type: ignore[no-untyped-def]
        create_module = getattr(self._wrapped_loader, "create_module", None)
        if callable(create_module):
            return create_module(spec)
        return None

    def exec_module(self, module):  # type: ignore[no-untyped-def]
        self._wrapped_loader.exec_module(module)  # type: ignore[attr-defined]
        if module.__name__ == _RUNTIME_MODULE:
            _patch_runtime_module(module)


class _RuntimePostImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname != _RUNTIME_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or isinstance(spec.loader, _RuntimePostImportLoader):
            return spec
        spec.loader = _RuntimePostImportLoader(spec.loader)
        return spec


def _install_post_import_finder() -> bool:
    if getattr(sys, _POST_IMPORT_FINDER_ATTR, False):
        return False
    sys.meta_path.insert(0, _RuntimePostImportFinder())
    setattr(sys, _POST_IMPORT_FINDER_ATTR, True)
    return True


def install_fast_combat_narration_skip() -> bool:
    """Install a narrow runtime hook that skips blocking combat LLM narration in fast-direct mode."""
    runtime_module = sys.modules.get(_RUNTIME_MODULE)
    if isinstance(runtime_module, ModuleType) and _patch_runtime_module(runtime_module):
        return True
    return _install_post_import_finder()


# Keep a direct callable for tests and explicit reinstallation.
def force_install_fast_combat_narration_skip_for_tests() -> bool:
    runtime_module = sys.modules.get(_RUNTIME_MODULE)
    if isinstance(runtime_module, ModuleType):
        original = getattr(runtime_module, _ORIGINAL_ATTR, None)
        if callable(original):
            setattr(runtime_module, "_apply_combat_narration_if_needed", original)
        original_apply_turn = getattr(runtime_module, _ORIGINAL_APPLY_TURN_ATTR, None)
        if callable(original_apply_turn):
            setattr(runtime_module, "apply_turn", original_apply_turn)
        if hasattr(runtime_module, _PATCH_ATTR):
            setattr(runtime_module, _PATCH_ATTR, False)
        return _patch_runtime_module(runtime_module)
    return install_fast_combat_narration_skip()
