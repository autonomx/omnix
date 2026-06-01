"""Canonical RPG session runtime facade.

The implementation is split across runtime_partXX modules to keep file sizes
manageable while preserving the historical app.rpg.session.runtime import path.
"""
from __future__ import annotations

import sys as _sys
from importlib import import_module as _import_module
from types import ModuleType as _ModuleType

_PART_MODULE_NAMES = [
    'runtime_part01',
    'runtime_part02',
    'runtime_part03',
    'runtime_part04',
    'runtime_part05',
    'runtime_part06',
    'runtime_part07',
    'runtime_part08',
    'runtime_part09',
    'runtime_part10',
    'runtime_part11',
    'runtime_part12',
    'runtime_part13',
    'runtime_part14',
    'runtime_part15',
    'runtime_part16',
    'runtime_part17',
    'runtime_part18',
    'runtime_part19',
    'runtime_part20',
    'runtime_part21',
    'runtime_part22',
    'runtime_part23',
]
_PART_MODULES = [
    _import_module(f"{__package__}.{name}") for name in _PART_MODULE_NAMES
]
_RUNTIME_GLOBALS = {}
for _module in _PART_MODULES:
    _RUNTIME_GLOBALS.update(
        {
            _name: _value
            for _name, _value in _module.__dict__.items()
            if not _name.startswith("__")
        }
    )

for _module in _PART_MODULES:
    _module.__dict__.update(_RUNTIME_GLOBALS)

globals().update(_RUNTIME_GLOBALS)


class _RuntimeFacadeModule(_ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        for module in _PART_MODULES:
            if name in module.__dict__:
                module.__dict__[name] = value


_sys.modules[__name__].__class__ = _RuntimeFacadeModule

for _name in (
    "_import_module",
    "_module",
    "_name",
    "_value",
    "_RUNTIME_GLOBALS",
    "_ModuleType",
    "_RuntimeFacadeModule",
    "_sys",
):
    globals().pop(_name, None)
