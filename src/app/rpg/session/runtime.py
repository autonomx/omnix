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
    'runtime_part24',
    'runtime_part25',
    'runtime_part26',
    'runtime_part27',
    'runtime_part28',
    'runtime_part29',
    'runtime_part30',
    'runtime_part31',
    'runtime_part32',
    'runtime_part33',
    'runtime_part34',
    'runtime_part35',
    'runtime_part36',
    'runtime_part37',
    'runtime_part38',
    'runtime_part39',
    'runtime_part40',
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
            if not _name.startswith("__") and not _name.startswith("_base_")
        }
    )

_RUNTIME_WRAPPER_MANIFEST = {
    "part_modules": list(_PART_MODULE_NAMES),
    "final_apply_turn_authoritative_module": _RUNTIME_GLOBALS.get("_apply_turn_authoritative").__module__,
    "final_apply_attack_combat_action_module": _RUNTIME_GLOBALS.get("_apply_attack_combat_action").__module__,
    "combat_contract_modules": [
        "app.rpg.session.runtime_part22",
        "app.rpg.session.runtime_part23",
        "app.rpg.session.runtime_part24",
        "app.rpg.session.runtime_part25",
        "app.rpg.session.runtime_part26",
    ],
}
_EXPECTED_RUNTIME_WRAPPER_MANIFEST = {
    "combat_contract_modules": [
        "app.rpg.session.runtime_part22",
        "app.rpg.session.runtime_part23",
        "app.rpg.session.runtime_part24",
        "app.rpg.session.runtime_part25",
        "app.rpg.session.runtime_part26",
    ],
    "final_apply_turn_authoritative_module": "app.rpg.session.runtime_part39",
    "final_apply_attack_combat_action_module": "app.rpg.session.runtime_part23",
}


def get_runtime_wrapper_manifest(_manifest: dict = _RUNTIME_WRAPPER_MANIFEST) -> dict:
    """Return the deterministic session runtime wrapper/load manifest."""
    return {
        "part_modules": list(_manifest["part_modules"]),
        "final_apply_turn_authoritative_module": _manifest["final_apply_turn_authoritative_module"],
        "final_apply_attack_combat_action_module": _manifest["final_apply_attack_combat_action_module"],
        "combat_contract_modules": list(_manifest["combat_contract_modules"]),
    }


def get_runtime_wrapper_drift_report(
    _manifest: dict = _RUNTIME_WRAPPER_MANIFEST,
    _expected: dict = _EXPECTED_RUNTIME_WRAPPER_MANIFEST,
) -> dict:
    """Return a JSON-safe report describing runtime wrapper manifest drift."""
    current_modules = list(_manifest["combat_contract_modules"])
    expected_modules = list(_expected["combat_contract_modules"])
    return {
        "ok": (
            current_modules == expected_modules
            and _manifest["final_apply_turn_authoritative_module"]
            == _expected["final_apply_turn_authoritative_module"]
            and _manifest["final_apply_attack_combat_action_module"]
            == _expected["final_apply_attack_combat_action_module"]
        ),
        "expected_combat_contract_modules": expected_modules,
        "actual_combat_contract_modules": current_modules,
        "missing_combat_contract_modules": [
            module for module in expected_modules if module not in current_modules
        ],
        "unexpected_combat_contract_modules": [
            module for module in current_modules if module not in expected_modules
        ],
        "final_apply_turn_authoritative_module": _manifest[
            "final_apply_turn_authoritative_module"
        ],
        "expected_final_apply_turn_authoritative_module": _expected[
            "final_apply_turn_authoritative_module"
        ],
        "final_apply_attack_combat_action_module": _manifest[
            "final_apply_attack_combat_action_module"
        ],
        "expected_final_apply_attack_combat_action_module": _expected[
            "final_apply_attack_combat_action_module"
        ],
    }


globals().update(_RUNTIME_GLOBALS)

# Mirror the final facade globals back into every split module so functions whose
# global namespace lives in runtime_partXX can resolve helpers defined by other
# parts. This intentionally skips dunder/private base aliases used by wrappers.
for _module in _PART_MODULES:
    if not isinstance(_module, _ModuleType):
        continue
    for _name, _value in _RUNTIME_GLOBALS.items():
        if _name.startswith("__") or _name.startswith("_base_"):
            continue
        setattr(_module, _name, _value)

# Preserve historical module identity in introspection-heavy tests.
_sys.modules[__name__] = _sys.modules[__name__]

__all__ = [name for name in globals() if not name.startswith("__")]
