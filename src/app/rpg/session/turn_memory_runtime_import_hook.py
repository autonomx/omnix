from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys

from app.rpg.session.turn_memory_player_agency_hook import preserve_player_agency_hook

_INTERACTIVE_MODULE = "app.rpg.session.interactive_first_call_runtime"
_POST_IMPORT_FINDER_ATTR = "_phase1433_turn_memory_runtime_finder_installed"


class InteractivePostImportLoader(importlib.abc.Loader):
    def __init__(self, wrapped_loader: importlib.abc.Loader):
        self._wrapped_loader = wrapped_loader

    def create_module(self, spec):  # type: ignore[no-untyped-def]
        create_module = getattr(self._wrapped_loader, "create_module", None)
        return create_module(spec) if callable(create_module) else None

    def exec_module(self, module):  # type: ignore[no-untyped-def]
        from app.rpg.session.turn_memory_runtime_patch import patch_interactive_module

        self._wrapped_loader.exec_module(module)  # type: ignore[attr-defined]
        if module.__name__ == _INTERACTIVE_MODULE:
            preserve_player_agency_hook(module)
            patch_interactive_module(module)


class InteractivePostImportFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname != _INTERACTIVE_MODULE:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or isinstance(spec.loader, InteractivePostImportLoader):
            return spec
        spec.loader = InteractivePostImportLoader(spec.loader)
        return spec


def install_post_import_finder() -> bool:
    if getattr(sys, _POST_IMPORT_FINDER_ATTR, False):
        return False
    sys.meta_path.insert(0, InteractivePostImportFinder())
    setattr(sys, _POST_IMPORT_FINDER_ATTR, True)
    return True
