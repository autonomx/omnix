"""Deterministic behavior capture for pre-refactor characterization scenarios."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable


GOLDEN_DIR = Path(__file__).with_name("golden")
_SCENARIO_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_UUID = re.compile(
    r"(?i)(?:\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b[0-9a-f]{32}\b)"
)
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
)
_TIMESTAMP_FIELDS = {"timestamp", "time_stamp", "created_at", "updated_at", "started_at", "ended_at"}
_DURATION_FIELDS = {"duration", "elapsed", "latency"}


def _stable_uuid(value: str, identities: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(0).lower()
        placeholder = identities.setdefault(raw, f"uuid:{len(identities) + 1}")
        return f"<{placeholder}>"

    return _UUID.sub(replace, value)


def _normalize(value: Any, *, field: str | None, identities: dict[str, str]) -> Any:
    if field is not None:
        normalized_field = field.casefold()
        if normalized_field in _TIMESTAMP_FIELDS or normalized_field.endswith(("_timestamp", "_at")):
            return "<timestamp>"
        if (
            normalized_field in _DURATION_FIELDS
            or normalized_field.endswith(
                ("_duration", "_elapsed", "_latency", "_ms", "_seconds")
            )
        ):
            return "<duration>"

    if isinstance(value, (datetime, date)):
        return "<timestamp>"
    if isinstance(value, str):
        if _TIMESTAMP.fullmatch(value):
            return "<timestamp>"
        return _stable_uuid(value, identities)
    if isinstance(value, float):
        rounded = round(value, 6)
        return 0.0 if rounded == 0 else rounded
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value, key=lambda item: str(item)):
            normalized_key = _stable_uuid(str(key), identities)
            normalized[normalized_key] = _normalize(
                value[key], field=str(key), identities=identities
            )
        return normalized
    if isinstance(value, (set, frozenset)):
        normalized_items = [
            _normalize(item, field=None, identities=identities) for item in value
        ]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, (list, tuple)):
        return [_normalize(item, field=None, identities=identities) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            payload = model_dump(mode="json")
        except TypeError:
            payload = model_dump()
        return _normalize(payload, field=field, identities=identities)
    return value


def normalize(value: Any) -> Any:
    """Strip unstable time/UUID/duration values and sort unordered collections."""

    return _normalize(value, field=None, identities={})


def _golden_path(scenario_name: str) -> Path:
    if not _SCENARIO_NAME.fullmatch(scenario_name):
        raise ValueError(f"invalid characterization scenario name: {scenario_name!r}")
    return GOLDEN_DIR / f"{scenario_name}.json"


def _serialize(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _difference_summary(expected: Any, actual: Any, *, limit: int = 20) -> list[str]:
    differences: list[str] = []

    def visit(path: str, left: Any, right: Any) -> None:
        if len(differences) >= limit:
            return
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right), key=str):
                child = f"{path}.{key}" if path else str(key)
                if key not in left:
                    differences.append(f"{child}: unexpected {right[key]!r}")
                elif key not in right:
                    differences.append(f"{child}: missing (expected {left[key]!r})")
                else:
                    visit(child, left[key], right[key])
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                child = f"{path}[{index}]"
                if index >= len(left):
                    differences.append(f"{child}: unexpected {right[index]!r}")
                elif index >= len(right):
                    differences.append(f"{child}: missing (expected {left[index]!r})")
                else:
                    visit(child, left[index], right[index])
            return
        if left != right:
            differences.append(f"{path}: expected {left!r}, got {right!r}")

    visit("", expected, actual)
    if len(differences) == limit:
        differences.append("additional differences omitted")
    return differences


def capture(scenario_name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Capture a scenario, write its golden only on explicit opt-in, then compare."""

    actual = normalize(fn())
    if not isinstance(actual, dict):
        raise TypeError("characterization scenarios must return a dictionary")

    path = _golden_path(scenario_name)
    if os.environ.get("OMNIX_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_serialize(actual), encoding="utf-8")
        return actual

    if not path.is_file():
        raise AssertionError(
            f"missing characterization golden {path}; introduce it with "
            "OMNIX_UPDATE_GOLDEN=1 before refactoring the scenario"
        )
    expected = json.loads(path.read_text(encoding="utf-8"))
    if actual != expected:
        raise AssertionError(
            f"characterization changed for {scenario_name}:\n"
            + "\n".join(f"- {item}" for item in _difference_summary(expected, actual))
        )
    return actual
