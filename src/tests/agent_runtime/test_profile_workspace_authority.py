from __future__ import annotations

from app.agent_runtime.profiles import list_agent_profiles


def test_every_profile_with_local_capabilities_requires_explicit_workspace() -> None:
    for profile in list_agent_profiles():
        if profile.capabilities:
            assert profile.requires_workspace, profile.id
