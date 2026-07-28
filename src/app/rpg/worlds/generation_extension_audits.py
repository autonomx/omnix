"""Late-roadmap World Forge audit registrations."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .generation_information_locality import (
    information_locality_report,
    require_valid_information_locality,
)
from .generation_route_effects import require_valid_route_effects, route_effect_report

ReportFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], dict[str, Any]]
RequireFn = Callable[[Sequence[Mapping[str, Any]], Mapping[str, Any] | None], Any]


def extension_audits() -> tuple[tuple[str, ReportFn, RequireFn], ...]:
    return (
        ("route_effects", route_effect_report, require_valid_route_effects),
        (
            "information_locality",
            information_locality_report,
            require_valid_information_locality,
        ),
    )


__all__ = ["extension_audits"]
