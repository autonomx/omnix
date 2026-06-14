from __future__ import annotations

import sys
from types import ModuleType

from app.rpg.session.turn_memory_runtime_patch import (
    _INTERACTIVE_MODULE,
    _ORIGINAL_APPLY_TURN_ATTR,
    _PATCH_ATTR,
    patch_interactive_module,
)


def force_install_turn_memory_runtime_hook_for_tests(module: ModuleType | None = None) -> bool:
    if module is None:
        module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        original = getattr(module, _ORIGINAL_APPLY_TURN_ATTR, None)
        if callable(original):
            setattr(module, "apply_turn", original)
        if hasattr(module, _PATCH_ATTR):
            setattr(module, _PATCH_ATTR, False)
        return patch_interactive_module(module)
    from app.rpg.session.turn_memory_runtime_hook import install_turn_memory_runtime_hook

    return install_turn_memory_runtime_hook()
