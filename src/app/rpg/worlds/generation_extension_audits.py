"""Late-roadmap World Forge audit registrations."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .generation_route_effects import require_valid_route_effects, route_effect_report

ReportFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], dict[str, Any]]
RequireFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], Any]


def extension_audits() -> tuple[tuple[str, ReportFn, RequireFn], ...]:
    return (
        ("route_effects", route_effect_report, require_valid_route_effects),
    )


__all__ = ["extension_audits"]
