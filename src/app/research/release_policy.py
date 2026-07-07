"""Release controls for Web Research capabilities."""
from __future__ import annotations

import hashlib
import os
from typing import Literal

from pydantic import BaseModel, Field

from .contracts import ResearchMode
from .settings import ResearchRuntimeSettings

ReleaseDecisionStatus = Literal["allowed", "downgraded", "unavailable"]


class ResearchReleasePolicy(BaseModel):
    master_enabled: bool = True
    quick_enabled: bool = True
    quick_percentage: int = Field(default=100, ge=0, le=100)
    deep_local_enabled: bool = True
    deep_local_percentage: int = Field(default=100, ge=0, le=100)
    hermes_enabled: bool = False
    hermes_percentage: int = Field(default=0, ge=0, le=100)


class ResearchReleaseDecision(BaseModel):
    requested_mode: ResearchMode
    effective_mode: ResearchMode
    status: ReleaseDecisionStatus
    reason: str
    warnings: list[str] = Field(default_factory=list)
    use_hermes_planner: bool = False


class ResearchReleaseAvailability(BaseModel):
    disabled: bool = True
    quick: bool
    deep: bool
    hermes_planner: bool


def research_release_policy_from_env() -> ResearchReleasePolicy:
    return ResearchReleasePolicy(
        master_enabled=_env_bool("OMNIX_RESEARCH_ENABLED", True),
        quick_enabled=_env_bool("OMNIX_RESEARCH_QUICK_ENABLED", True),
        quick_percentage=_env_percent("OMNIX_RESEARCH_QUICK_PERCENT", 100),
        deep_local_enabled=_env_bool("OMNIX_RESEARCH_DEEP_LOCAL_ENABLED", True),
        deep_local_percentage=_env_percent("OMNIX_RESEARCH_DEEP_LOCAL_PERCENT", 100),
        hermes_enabled=_env_bool("OMNIX_RESEARCH_HERMES_ROLLOUT_ENABLED", False),
        hermes_percentage=_env_percent("OMNIX_RESEARCH_HERMES_PERCENT", 0),
    )


def research_release_availability(
    settings: ResearchRuntimeSettings,
    policy: ResearchReleasePolicy,
    *,
    identity: str,
) -> ResearchReleaseAvailability:
    quick = _quick_available(settings, policy, identity)
    deep = _deep_available(settings, policy, identity)
    hermes = (
        deep
        and settings.hermes_planner_enabled
        and policy.hermes_enabled
        and _in_cohort(identity, policy.hermes_percentage, "hermes")
    )
    return ResearchReleaseAvailability(
        quick=quick,
        deep=deep,
        hermes_planner=hermes,
    )
