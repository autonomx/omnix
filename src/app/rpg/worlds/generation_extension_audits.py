"""Late-roadmap World Forge audit registrations."""
from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .generation_information_locality import (
    information_locality_report,
    require_valid_information_locality,
)
from .generation_local_narrative import (
    local_narrative_report,
    require_valid_local_narrative,
)
from .generation_route_effects import require_valid_route_effects, route_effect_report
from .generation_starting_market import (
    require_valid_starting_market,
    starting_market_report,
)
from .generation_starter_core_locations import (
    require_valid_starter_core_locations,
    starter_core_location_report,
)
from .generation_starter_region import (
    require_valid_starter_region,
    starter_region_report,
)
from .generation_starter_topology import (
    require_valid_starter_topology,
    starter_topology_report,
)

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
        (
            "local_narrative",
            local_narrative_report,
            require_valid_local_narrative,
        ),
        (
            "starting_market",
            starting_market_report,
            require_valid_starting_market,
        ),
        (
            "starter_topology",
            starter_topology_report,
            require_valid_starter_topology,
        ),
        (
            "starter_region",
            starter_region_report,
            require_valid_starter_region,
        ),
        (
            "starter_core_locations",
            starter_core_location_report,
            require_valid_starter_core_locations,
        ),
    )


__all__ = ["extension_audits"]
