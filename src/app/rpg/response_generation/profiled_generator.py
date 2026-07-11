from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .orchestration import RpgResponseGenerator
from .performance import blocking_path_decision
from .profiles import ResponseGenerationProfile, ResponseProfileRegistry


class ProfiledRpgResponseGenerator:
    """Apply the authoritative profile and blocking policy to canonical output."""

    def __init__(
        self,
        generator: RpgResponseGenerator | None = None,
        registry: ResponseProfileRegistry | None = None,
    ) -> None:
        self.generator = generator or RpgResponseGenerator()
        self.registry = registry or ResponseProfileRegistry()

    def generate(self, request):
        rendered = self.generator.generate(request)
        result = _mapping(request.authoritative_turn_result)
        recovery_needed = bool(
            result.get("recovery_needed")
            or result.get("resolver_status") in {"unresolved", "partial"}
            or rendered.mode.value in {"recovery", "investigation"}
            and request.runtime_mode not in {"supported_mechanic", "utility"}
        )
        profile, ignored = self.registry.resolve_from_request(
            rendered.mode,
            request.provider_policy,
            recovery_needed=recovery_needed,
        )
        path = blocking_path_decision(
            rendered.mode,
            profile,
            supported_mechanic=bool(
                result.get("mechanic_resolved")
                or result.get("supported_mechanic")
                or request.runtime_mode in {"supported_mechanic", "utility"}
            ),
            recovery_needed=recovery_needed,
            cache_hit=bool(request.provider_policy.get("cache_hit")),
        )
        metadata = {
            **dict(rendered.metadata),
            "response_profile": profile.debug_payload(),
            "ignored_runtime_profile_overrides": list(ignored),
            "blocking_path": {
                "action": path.action,
                "reason": path.reason,
                "use_provider": path.use_provider,
                "use_hermes": path.use_hermes,
                "cacheable": path.cacheable,
                "blocking_budget_ms": path.blocking_budget_ms,
            },
            "validation_complete": True,
        }
        return replace(rendered, metadata=metadata)

    def resolve_profile(self, request, mode) -> ResponseGenerationProfile:
        result = _mapping(request.authoritative_turn_result)
        recovery_needed = bool(result.get("recovery_needed"))
        return self.registry.resolve_from_request(
            mode,
            request.provider_policy,
            recovery_needed=recovery_needed,
        )[0]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
