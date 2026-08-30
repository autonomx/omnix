"""Built-in profiles compiled into immutable RunSpec authority."""
from __future__ import annotations

import re

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
        optional_external_capabilities=("github.read_repo", "weather.current"),
        context_sources=("assistant_memory",),
        requires_workspace=False,
    ),
    "personal-assistant": AgentProfile(id="personal-assistant", description="Governed email, calendar, and contacts.", external_capabilities=("gmail.read_email", "gmail.create_draft", "gmail.send_email", "calendar.read_availability", "calendar.create_event", "contacts.search_contacts", "contacts.resolve_recipient"), context_sources=("assistant_memory",)),
    "ops": AgentProfile(id="ops", description="Workspace-scoped diagnostics and controlled commands.", capabilities=(*_READ, "workspace.command", "workspace.test"), requires_workspace=True),
    "trading-research": AgentProfile(
        id="trading-research",
        description="Read-only market investigation using governed research services; broker/order mutation authority is intentionally absent.",
        external_capabilities=("research.web_search", "trading.market_quote"),
        optional_external_capabilities=("market.status",),
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


def profile_external_ceiling(profile: AgentProfile) -> set[str]:
    """Maximum external authority a task compiled for this profile may receive."""
    return set(profile.external_capabilities) | set(profile.optional_external_capabilities)


def resolve_profile_capabilities(profile: AgentProfile, *, requested: list[str] | None = None, requested_external: list[str] | None = None) -> tuple[list[str], list[str]]:
    local_allowed = set(profile.capabilities)
    external_allowed = profile_external_ceiling(profile)
    local = list(profile.capabilities) if requested is None else list(dict.fromkeys(requested))
    # Profiles are ceilings, not grants. External authority is issued only when
    # a compiled task explicitly requests it.
    external = [] if requested_external is None else list(dict.fromkeys(requested_external))
    if not set(local).issubset(local_allowed):
        raise ValueError("requested local capabilities exceed selected profile")
    if not set(external).issubset(external_allowed):
        raise ValueError("requested external capabilities exceed selected profile")
    return local, external


_CODE_STRONG_INTENT = re.compile(
    r"(?:\b(?:code|codebase|repo(?:sitory)?|pull request|pytest|vitest|workspace|git|"
    r"selector|classname|css|html|stylesheet|tsx?|jsx?|ui|ux|frontend|backend|"
    r"middleware|callback|handler|hook|endpoint)\b|"
    r"(?<!\w)[.#]?(?:[A-Za-z][A-Za-z0-9_]*-){2,}[A-Za-z][A-Za-z0-9_]*|"
    r"(?:^|[\\/])(?:src|app|tests?|packages?|components?)[\\/][^\s]+|"
    r"\b[A-Za-z0-9_.-]+\.(?:py|pyi|js|jsx|ts|tsx|go|rs|java|rb|php|cs|cpp|c|h)\b)",
    re.I,
)
_CODE_ACTION_TARGET = re.compile(
    r"\b(?:fix|debugg?|diagnose|inspect|review|edit|modify|change|update|refactor|implement|"
    r"trace|test|build|lint|typecheck)\b.{0,100}"
    r"\b(?:bugs?|tests?|router|api|module|function|source|migration|schema)\b",
    re.I,
)
_UI_CODE_CONTEXT = re.compile(
    r"(?:\b(?:app|ui|ux|frontend|web|page|screen|interface|react|vue|css|html|omnix)\b"
    r".{0,100}\b(?:button|icon|element|component|layout|menu|modal|dropdown|tab|sidebar|"
    r"header|footer|form|input|textarea|dialog|tooltip|badge|chip)\b|"
    r"\b(?:button|icon|element|component|layout|menu|modal|dropdown|tab|sidebar|"
    r"header|footer|form|input|textarea|dialog|tooltip|badge|chip)\b"
    r".{0,100}\b(?:app|ui|ux|frontend|web|page|screen|interface|react|vue|css|html|omnix)\b)",
    re.I,
)
_UI_THEME_CONTEXT = re.compile(
    r"(?:\b(?:light|dark)\s+mode\b|"
    r"\b(?:theme|themes|theming|stylesheet|stylesheets|color\s+scheme|colour\s+scheme)\b|"
    r"\b(?:aurora|liquid\s+glass)\b.{0,80}\b(?:mode|theme|style|styles|styling)\b|"
    r"\b(?:mode|theme|style|styles|styling)\b.{0,80}\b(?:aurora|liquid\s+glass)\b)",
    re.I,
)
_UI_THEME_ACTION = re.compile(
    r"\b(?:fix|debugg?|diagnose|inspect|review|check|edit|modify|change|update|refactor|implement|"
    r"test|build|adjust|improve|apply|style|restyle)\b",
    re.I,
)
_REPO_OPS_INTENT = re.compile(
    r"(?:\bgithub\b.{0,60}\b(?:ci|actions?|workflows?|checks?|pull request|repo(?:sitory)?)\b|"
    r"\b(?:ci|workflow checks?|github actions?)\b|"
    r"\b(?:push|commit|checkout|rebase|merge)\b.{0,80}\b(?:branch|repo(?:sitory)?|git)\b|"
    r"\b(?:branch|repo(?:sitory)?|git)\b.{0,80}\b(?:push|commit|checkout|rebase|merge)\b)",
    re.I,
)
_HOME_INTENT = re.compile(r"\b(?:kasa|smart\s+plugs?|plugs?|outlets?|lamps?|lights?|thermostats?|home)\b", re.I)
_HOME_TASK_INTENT = re.compile(
    r"\b(?:turn|set|adjust|lower|raise|check|inspect|fix|change|dim|brighten)\b"
    r".{0,100}\b(?:kasa|smart\s+plugs?|plugs?|outlets?|lamps?|lights?|thermostats?|home)\b",
    re.I,
)
_PERSONAL_INTENT = re.compile(r"\b(?:gmail|emails?|calendars?|meetings?|contacts?|appointments?|schedules?)\b", re.I)
_PERSONAL_TASK_INTENT = re.compile(
    r"\b(?:check|inspect|read|summarize|find|look\s+up|draft|send|reply|forward|"
    r"schedule|book|create|cancel)\b.{0,100}"
    r"\b(?:gmail|emails?|calendars?|meetings?|contacts?|appointments?|schedules?)\b",
    re.I,
)
_TRADING_INTENT = re.compile(
    r"\b(?:stocks?|trading|trades?|tickers?|markets?|shares?|equities|gainers?|losers?|"
    r"orders?|positions?|buy|sell|purchase|short|cover|nvda|gme|tsla)\b",
    re.I,
)
_TRADING_TASK_INTENT = re.compile(
    r"\b(?:research|investigate|analy[sz]e|check|quote|price|buy|sell|purchase|short|cover|"
    r"place|submit|cancel)\b.{0,100}"
    r"\b(?:stocks?|trading|trades?|tickers?|markets?|shares?|equities|gainers?|losers?|"
    r"orders?|positions?|nvda|gme|tsla)\b",
    re.I,
)


def select_agent_profile_id(content: str) -> str:
    """Shared deterministic profile precedence used by Chat and steering.

    Domain-bound actions outrank generic vocabulary. Coding is selected by
    software/workspace evidence or contextual UI work, not by generic verbs
    such as "fix" or nouns such as "button" in isolation.
    """
    text = str(content or "")
    theme_context = bool(_UI_THEME_CONTEXT.search(text))
    theme_task = bool(theme_context and _UI_THEME_ACTION.search(text))
    # UI/theme vocabulary must never fall through to the generic smart-home
    # noun "light". Actionable appearance work is coding; non-actionable theme
    # discussion defaults to research rather than House.
    if theme_context:
        return "coding" if theme_task else "research"
    if _HOME_TASK_INTENT.search(text):
        return "house"
    if _PERSONAL_TASK_INTENT.search(text):
        return "personal-assistant"
    if _TRADING_TASK_INTENT.search(text):
        return "trading-research"
    if (
        _CODE_STRONG_INTENT.search(text)
        or _CODE_ACTION_TARGET.search(text)
        or _UI_CODE_CONTEXT.search(text)
        or theme_task
        or _REPO_OPS_INTENT.search(text)
    ):
        return "coding"
    if _HOME_INTENT.search(text):
        return "house"
    if _PERSONAL_INTENT.search(text):
        return "personal-assistant"
    if _TRADING_INTENT.search(text):
        return "trading-research"
    return "research"
