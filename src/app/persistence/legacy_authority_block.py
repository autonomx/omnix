from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import sys
from types import ModuleType
from typing import Any

from .runtime import LegacyPersistenceRetired


RETIRED_MUTABLE_AUTHORITY_MODULES = frozenset(
    {
        "app.assist_core.policy_store",
        "app.assistant_tools.config_store",
        "app.chat.prompt_store",
        "app.gateway.live_chat_evaluation_store",
        "app.image.asset_store",
        "app.research.source_store",
        "app.rpg.narrative.narrative_persistence",
        "app.rpg.npc_evolution.profile_store",
    }
)

_MUTATOR_WORDS = (
    "append",
    "create",
    "delete",
    "import",
    "insert",
    "persist",
    "record",
    "remove",
    "replace",
    "save",
    "set",
    "store",
    "update",
    "upsert",
    "write",
)


class RetiredMutableAuthority:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise LegacyPersistenceRetired(
            "mutable JSON/manifest runtime authority is retired; use the matching "
            "PostgreSQL repository or the Phase 8 import tool"
        )


def _retired_call(*args: Any, **kwargs: Any) -> Any:
    del args, kwargs
    raise LegacyPersistenceRetired(
        "mutable JSON/manifest runtime authority is retired; use PostgreSQL"
    )


def _patch_module(module: ModuleType) -> None:
    for name, value in list(vars(module).items()):
        if name.startswith("_"):
            continue
        lowered = name.lower()
        if isinstance(value, type) and (
            lowered.endswith("store")
            or lowered.endswith("repository")
            or "manifest" in lowered
        ):
            setattr(module, name, RetiredMutableAuthority)
            continue
        if callable(value) and any(word in lowered for word in _MUTATOR_WORDS):
            setattr(module, name, _retired_call)
    setattr(module, "OMNIX_RUNTIME_AUTHORITY_RETIRED", True)


class _RetirementLoader(importlib.abc.Loader):
    def __init__(self, original: importlib.abc.Loader) -> None:
        self.original = original

    def create_module(self, spec):  # type: ignore[no-untyped-def]
        create = getattr(self.original, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module: ModuleType) -> None:
        self.original.exec_module(module)
        _patch_module(module)


class _RetirementFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path, target=None):  # type: ignore[no-untyped-def]
        if fullname not in RETIRED_MUTABLE_AUTHORITY_MODULES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        if isinstance(spec.loader, _RetirementLoader):
            return spec
        return importlib.util.spec_from_loader(
            fullname,
            _RetirementLoader(spec.loader),
            origin=spec.origin,
            is_package=spec.submodule_search_locations is not None,
        )


_FINDER = _RetirementFinder()


def install_legacy_authority_block() -> None:
    if _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)
    for module_name in RETIRED_MUTABLE_AUTHORITY_MODULES:
        module = sys.modules.get(module_name)
        if module is not None:
            _patch_module(module)
