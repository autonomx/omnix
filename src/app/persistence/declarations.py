"""Module declarations the kernel reads by convention (ADR-0016, PA-2.2).

A module's ``declarations.py`` sits next to its ``feature.py`` and imports only
kernel modules, so the kernel reads it without loading the module. The
retention worker and the capacity report find each module's record types
there, whether or not its feature is enabled, the way migrations are found
(PA-2.3)::

    RETENTION = (RetentionDeclaration("rpg_narration_events", delete=_delete_events, capacity_cleanup=True),)
    CAPACITY = (CapacityCount("rpg_turns", count=_count_turns),)

A declared record type's ``omnix_retention_policies`` row is seeded by a
migration; without one the type is never run.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

# (connection, retention_days, batch_size) -> rows deleted; one short transaction per call.
DeleteHandler = Callable[[Any, int, int], int]
RowCount = Callable[[Any], int]


@dataclass(frozen=True)
class RetentionDeclaration:
    """A retention record type a module owns, and how to delete its expired rows."""

    record_type: str
    delete: DeleteHandler
    # Also run by the lifecycle capacity cleanup, not only by the retention worker.
    capacity_cleanup: bool = False


@dataclass(frozen=True)
class CapacityCount:
    """A row count the capacity report shows."""

    name: str
    count: RowCount


def declaration_modules() -> tuple[str, ...]:
    """Every module's declarations: ``app/<package>/declarations.py`` or one level deeper, next to a feature.py."""
    app_root = Path(__file__).resolve().parents[1]
    found = sorted(
        path for pattern in ("*/declarations.py", "*/*/declarations.py") for path in app_root.glob(pattern)
        if (path.parent / "feature.py").is_file()
    )
    return tuple("app." + ".".join(path.relative_to(app_root).with_suffix("").parts) for path in found)


def _declared() -> tuple[Mapping[str, RetentionDeclaration], Mapping[str, CapacityCount]]:
    retention: dict[str, RetentionDeclaration] = {}
    capacity: dict[str, CapacityCount] = {}
    for name in declaration_modules():
        module = importlib.import_module(name)
        for declaration in getattr(module, "RETENTION", ()):
            if declaration.record_type in retention:
                raise ValueError(f"retention record type {declaration.record_type} is declared twice")
            retention[declaration.record_type] = declaration
        for counter in getattr(module, "CAPACITY", ()):
            if counter.name in capacity:
                raise ValueError(f"capacity count {counter.name} is declared twice")
            capacity[counter.name] = counter
    return MappingProxyType(retention), MappingProxyType(capacity)


def module_retention() -> Mapping[str, RetentionDeclaration]:
    return _declared()[0]


def module_capacity_counts() -> Mapping[str, CapacityCount]:
    return _declared()[1]
