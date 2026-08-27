"""Built-in profiles compiled into immutable RunSpec authority."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AgentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    description: str
    capabilities: tuple[str, ...] = ()
    external_capabilities: tuple[str, ...] = ()
    optional_external_capabilities: tuple[str, ...] = ()
    context_sources: tuple[str, ...] = ()
    requires_workspace: bool = False


_READ = ("workspace.read", "workspace.list", "workspace.search", "workspace.git_status", "workspace.git_diff")
_WRITE = ("workspace.edit", "workspace.write", "workspace.command", "workspace.test")
_PROFILES = {
    "coding": AgentProfile(
        id="coding",
        description="Repository-scoped software implementation and validation.",
        capabilities=(*_READ, *_WRITE),
        optional_external_capabilities=(
            "github.read_repo",
            "github.create_branch",
            "github.push",
            "github.create_pr",
            "github.inspect_ci",
            "github.merge_pr",
        ),
        requires_workspace=True,
    ),
    "house": AgentProfile(id="house", description="Semantic smart-home inspection and governed control.", external_capabilities=("home.list_devices", "home.get_state", "home.set_state", "home.get_energy", "home.apply_scene")),
    "research": AgentProfile(
        id="research",
        description="Read-only investigation using governed Omnix research services.",
        external_capabilities=("research.web_search",),
        optional_external_capabilities=("github.read_repo",),
        context_sources=("assistant_memory",),
        requires_workspace=False,
    ),
    "personal-assistant": AgentProfile(id="personal-assistant", description="Governed email, calendar, and contacts.", external_capabilities=("gmail.read_email", "gmail.create_draft", "gmail.send_email", "calendar.read_availability", "calendar.create_event", "contacts.search_contacts", "contacts.resolve_recipient"), context_sources=("assistant_memory",)),
    "ops": AgentProfile(id="ops", description="Workspace-scoped diagnostics and controlled commands.", capabilities=(*_READ, "workspace.command", "workspace.test"), requires_workspace=True),
    "trading-research": AgentProfile(
        id="trading-research",
        description="Read-only market investigation using governed research services; broker/order mutation authority is intentionally absent.",
        external_capabilities=("research.web_search",),
        context_sources=("trading_research", "assistant_memory"),
        requires_workspace=False,
    ),
}


def get_agent_profile(profile_id: str) -> AgentProfile:
    key = str(profile_id or "coding").strip().casefold()
    profile = _PROFILES.get(key)
    if profile is None:
        raise ValueError(f"unknown agent profile: {profile_id}")
    return profile


def list_agent_profiles() -> list[AgentProfile]:
    return list(_PROFILES.values())


def resolve_profile_capabilities(profile: AgentProfile, *, requested: list[str] | None = None, requested_external: list[str] | None = None) -> tuple[list[str], list[str]]:
    local_allowed = set(profile.capabilities)
    external_allowed = set(profile.external_capabilities) | set(
        profile.optional_external_capabilities
    )
    local = list(profile.capabilities) if requested is None else list(dict.fromkeys(requested))
    external = list(profile.external_capabilities) if requested_external is None else list(dict.fromkeys(requested_external))
    if not set(local).issubset(local_allowed):
        raise ValueError("requested local capabilities exceed selected profile")
    if not set(external).issubset(external_allowed):
        raise ValueError("requested external capabilities exceed selected profile")
    return local, external
