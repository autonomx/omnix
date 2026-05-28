"""BS.1 — runtime bridge for survival grounding in world_scene_narrator.

This module avoids rewriting the large legacy narrator monolith.  It patches the
loaded ``app.rpg.ai.world_scene_narrator`` module in-place so:

1. ``build_scene_prompt`` appends the survival narration grounding contract.
2. ``_sanitize_narration_payload`` performs the normal legacy sanitization first,
   then strips unsupported survival claims using the BS contract.

The patch is idempotent and can be applied eagerly to an already-loaded module or
through the package import hook in ``app.rpg.ai.__init__``.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
from types import ModuleType
from typing import Any, Dict

from app.rpg.ai.survival_narration_grounding import (
    build_survival_narration_evidence,
    sanitize_survival_narration_payload,
    survival_narration_prompt_block,
    validate_survival_narration_text,
)

_TARGET_MODULE = "app.rpg.ai.world_scene_narrator"
_PATCH_FLAG = "_BS1_SURVIVAL_GROUNDING_PATCHED"
_ORIGINAL_PROMPT_ATTR = "_bs1_original_build_scene_prompt"
_ORIGINAL_SANITIZE_ATTR = "_bs1_original_sanitize_narration_payload"
_HOOK_FLAG = "_BS1_SURVIVAL_GROUNDING_IMPORT_HOOK_INSTALLED"
_LEGACY_FALLBACK_TEXTS = {
    "the action resolves according to the current survival state.",
    "the action changes the scene, and the people nearby react according to what just happened.",
    "the survival action resolves.",
}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _has_survival_evidence(narration_context: Dict[str, Any]) -> bool:
    evidence = build_survival_narration_evidence(_safe_dict(narration_context))
    return bool(
        evidence.get("survival")
        or evidence.get("actions")
        or evidence.get("successful_actions")
        or evidence.get("blocked_actions")
        or evidence.get("effects")
        or evidence.get("inventory_delta")
        or evidence.get("backed_categories")
    )


def _is_legacy_survival_fallback(value: Any) -> bool:
    text = " ".join(_safe_str(value).split()).strip().lower()
    return text in _LEGACY_FALLBACK_TEXTS


def append_survival_grounding_to_prompt(prompt: str, narration_context: Dict[str, Any]) -> str:
    """Append the survival grounding contract only when evidence exists."""
    prompt = str(prompt or "")
    narration_context = _safe_dict(narration_context)
    if not _has_survival_evidence(narration_context):
        return prompt
    block = survival_narration_prompt_block(narration_context)
    if block and block not in prompt:
        return prompt.rstrip() + "\n\n" + block + "\n"
    return prompt


def sanitize_world_scene_survival_payload(payload: Dict[str, Any], narration_context: Dict[str, Any]) -> Dict[str, Any]:
    """Apply BS survival sanitizer while preserving existing narrator metadata."""
    payload = dict(_safe_dict(payload))
    narration_context = _safe_dict(narration_context)
    if not _has_survival_evidence(narration_context):
        return payload
    sanitized = sanitize_survival_narration_payload(payload, narration_context)
    # Preserve existing grounding metadata from the older presentation validator.
    for key in ("grounding_validation", "grounding_fallback", "grounding_fallback_reason"):
        if key in payload and key not in sanitized:
            sanitized[key] = payload[key]
    return sanitized


def _merge_bs1_sanitized_payload(
    *,
    original_payload: Dict[str, Any],
    legacy_payload: Dict[str, Any],
    narration_context: Dict[str, Any],
) -> Dict[str, Any]:
    """Run BS after legacy sanitize, salvaging grounded original sentences if legacy over-fell back."""
    legacy_payload = dict(_safe_dict(legacy_payload))
    narration_context = _safe_dict(narration_context)
    original_payload = dict(_safe_dict(original_payload))

    sanitized = sanitize_world_scene_survival_payload(legacy_payload, narration_context)
    original_sanitized = sanitize_world_scene_survival_payload(original_payload, narration_context)

    if _is_legacy_survival_fallback(sanitized.get("narration")):
        original_narration = _safe_str(original_sanitized.get("narration")).strip()
        if original_narration and not _is_legacy_survival_fallback(original_narration):
            validation = validate_survival_narration_text(original_narration, narration_context)
            if validation.get("ok"):
                sanitized["narration"] = original_narration

    # Preserve the most complete BS grounding record after any salvage.
    combined_text = " ".join(
        [
            _safe_str(sanitized.get("narration")),
            _safe_str(sanitized.get("action")),
            _safe_str(_safe_dict(sanitized.get("npc")).get("line")),
        ]
    )
    validation = validate_survival_narration_text(combined_text, narration_context)
    sanitized["survival_narration_grounding"] = {
        "ok": validation.get("ok"),
        "violations": validation.get("violations"),
        "evidence": validation.get("evidence"),
        "source": "survival_narration_grounding_contract",
        "legacy_salvage_checked": True,
    }
    return sanitized


def patch_world_scene_narrator_module(module: ModuleType) -> ModuleType:
    """Patch a loaded world_scene_narrator module in-place."""
    if getattr(module, _PATCH_FLAG, False):
        return module

    original_prompt = getattr(module, "build_scene_prompt", None)
    original_sanitize = getattr(module, "_sanitize_narration_payload", None)
    if not callable(original_prompt) or not callable(original_sanitize):
        return module

    setattr(module, _ORIGINAL_PROMPT_ATTR, original_prompt)
    setattr(module, _ORIGINAL_SANITIZE_ATTR, original_sanitize)

    def build_scene_prompt(scene, narration_context, tone="dramatic"):
        prompt = original_prompt(scene, narration_context, tone=tone)
        return append_survival_grounding_to_prompt(prompt, _safe_dict(narration_context))

    def _sanitize_narration_payload(payload, scene, narration_context, authoritative_action=None):
        sanitized = original_sanitize(
            payload,
            scene,
            narration_context,
            authoritative_action=authoritative_action,
        )
        return _merge_bs1_sanitized_payload(
            original_payload=_safe_dict(payload),
            legacy_payload=_safe_dict(sanitized),
            narration_context=_safe_dict(narration_context),
        )

    build_scene_prompt.__name__ = "build_scene_prompt"
    build_scene_prompt.__doc__ = (getattr(original_prompt, "__doc__", "") or "") + "\n\nBS.1 survival grounding bridge active."
    _sanitize_narration_payload.__name__ = "_sanitize_narration_payload"
    _sanitize_narration_payload.__doc__ = (getattr(original_sanitize, "__doc__", "") or "") + "\n\nBS.1 survival grounding bridge active."

    setattr(module, "build_scene_prompt", build_scene_prompt)
    setattr(module, "_sanitize_narration_payload", _sanitize_narration_payload)
    setattr(module, _PATCH_FLAG, True)
    return module


class _SurvivalGroundingLoader(importlib.abc.Loader):
    def __init__(self, wrapped: importlib.abc.Loader):
        self._wrapped = wrapped

    def create_module(self, spec):  # pragma: no cover - delegates to importlib
        create_module = getattr(self._wrapped, "create_module", None)
        if callable(create_module):
            return create_module(spec)
        return None

    def exec_module(self, module):
        self._wrapped.exec_module(module)
        patch_world_scene_narrator_module(module)


class _SurvivalGroundingFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname != _TARGET_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None or isinstance(spec.loader, _SurvivalGroundingLoader):
            return spec
        spec.loader = _SurvivalGroundingLoader(spec.loader)
        return spec


def install_world_scene_survival_grounding_hook() -> bool:
    """Install the lazy import hook and patch an already-loaded narrator."""
    if _TARGET_MODULE in sys.modules:
        patch_world_scene_narrator_module(sys.modules[_TARGET_MODULE])

    if getattr(sys, _HOOK_FLAG, False):
        return True
    sys.meta_path.insert(0, _SurvivalGroundingFinder())
    setattr(sys, _HOOK_FLAG, True)
    return True


def force_patch_world_scene_narrator() -> ModuleType:
    """Import and patch the narrator immediately. Intended for focused tests."""
    module = importlib.import_module(_TARGET_MODULE)
    return patch_world_scene_narrator_module(module)
