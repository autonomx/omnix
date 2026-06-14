from __future__ import annotations

import sys
from types import ModuleType

from app.rpg.session.turn_memory_runtime_attach import attach_turn_memory_to_runtime_result
from app.rpg.session.turn_memory_runtime_import_hook import install_post_import_finder, preserve_player_agency_hook
from app.rpg.session.turn_memory_runtime_patch import (
    force_install_turn_memory_runtime_hook_for_tests,
    patch_interactive_module,
)

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"


def install_turn_memory_runtime_hook() -> bool:
    module = sys.modules.get(_INTERACTIVE_MODULE)
    if isinstance(module, ModuleType):
        preserve_player_agency_hook(module)
        if patch_interactive_module(module):
            return True
    return install_post_import_finder()


__all__ = [
    "attach_turn_memory_to_runtime_result",
    "force_install_turn_memory_runtime_hook_for_tests",
    "install_turn_memory_runtime_hook",
    "patch_interactive_module",
]
