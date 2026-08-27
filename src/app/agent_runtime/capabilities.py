"""Canonical Omnix capability registry.

Capabilities describe authority independently from any one planner/runtime. Hermes,
Pi, the browser UI, and policy code consume projections of this catalog instead
of maintaining runtime-specific tool names.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CapabilityExecutionZone = Literal["worker", "broker", "model", "context"]
CapabilityEffect = Literal["read", "create", "mutate", "delete", "execute"]
CapabilityRisk = Literal["low", "medium", "high"]
CapabilityApproval = Literal["allow_automatic", "ask_sensitive", "always_ask", "disabled"]


class Capability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    description: str
    namespace: str
    execution_zone: CapabilityExecutionZone
    effect: CapabilityEffect
    risk: CapabilityRisk = "low"
    scope_type: str = "workspace"
    approval_policy: CapabilityApproval = "allow_automatic"
    network_required: bool = False
    credential_required: bool = False
    audited: bool = True
    enabled: bool = True
    requires_connection: bool = False
    requires_confirmation: bool = False
    destructive: bool = False
    provider: str | None = None
    category: str = "general"
    assistant_visible: bool = False
    hermes_visible: bool = False
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    aliases: tuple[str, ...] = ()


class CapabilityRegistry:
    def __init__(self, capabilities: Iterable[Capability]) -> None:
        rows = list(capabilities)
        ids = [row.id for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate capability id")
        self._by_id = {row.id: row for row in rows}
        self._aliases: dict[str, str] = {}
        for row in rows:
            for alias in row.aliases:
                if alias in self._aliases or alias in self._by_id:
                    raise ValueError(f"duplicate capability alias: {alias}")
                self._aliases[alias] = row.id

    def all(self) -> list[Capability]:
        return list(self._by_id.values())

    def get(self, capability_id: str) -> Capability | None:
        canonical = self._aliases.get(capability_id, capability_id)
        return self._by_id.get(canonical)

    def canonical_id(self, capability_id: str) -> str | None:
        row = self.get(capability_id)
        return row.id if row is not None else None

    def for_namespace(self, namespace: str) -> list[Capability]:
        return [row for row in self._by_id.values() if row.namespace == namespace]

    def assistant_projection(self) -> list[Capability]:
        return [row for row in self._by_id.values() if row.assistant_visible]

    def hermes_projection(self) -> list[Capability]:
        return [row for row in self._by_id.values() if row.hermes_visible]


def _cap(
    capability_id: str,
    name: str,
    description: str,
    *,
    zone: CapabilityExecutionZone,
    effect: CapabilityEffect,
    risk: CapabilityRisk = "low",
    namespace: str | None = None,
    scope_type: str = "workspace",
    approval: CapabilityApproval | None = None,
    network: bool = False,
    credentials: bool = False,
    connection: bool = False,
    confirmation: bool = False,
    destructive: bool = False,
    provider: str | None = None,
    category: str = "general",
    assistant: bool = False,
    hermes: bool = False,
    input_schema: dict[str, Any] | None = None,
    aliases: tuple[str, ...] = (),
) -> Capability:
    ns = namespace or capability_id.split(".", 1)[0]
    if approval is None:
        if destructive or confirmation or risk == "high":
            approval = "always_ask"
        elif effect in {"create", "mutate", "delete", "execute"} or risk == "medium":
            approval = "ask_sensitive"
        else:
            approval = "allow_automatic"
    return Capability(
        id=capability_id,
        name=name,
        description=description,
        namespace=ns,
        execution_zone=zone,
        effect=effect,
        risk=risk,
        scope_type=scope_type,
        approval_policy=approval,
        network_required=network,
        credential_required=credentials,
        requires_connection=connection,
        requires_confirmation=confirmation,
        destructive=destructive,
        provider=provider,
        category=category,
        assistant_visible=assistant,
        hermes_visible=hermes,
        input_schema=input_schema or {},
        aliases=aliases,
    )


_DEFAULT_CAPABILITIES = (
    _cap("workspace.read", "Read workspace file", "Read a UTF-8 file within the issued workspace scope.", zone="worker", effect="read", category="development", input_schema={"path": "workspace-relative path"}),
    _cap("workspace.list", "List workspace", "List entries within the issued workspace scope.", zone="worker", effect="read", category="development", input_schema={"path": "workspace-relative directory"}),
    _cap("workspace.search", "Search workspace", "Search text within the issued workspace scope.", zone="worker", effect="read", category="development", input_schema={"query": "string", "path": "workspace-relative path"}),
    _cap("workspace.edit", "Edit workspace file", "Apply a bounded text replacement inside the issued workspace.", zone="worker", effect="mutate", risk="medium", category="development", input_schema={"path": "workspace-relative path"}),
    _cap("workspace.write", "Write workspace file", "Write a file inside the issued workspace.", zone="worker", effect="mutate", risk="medium", category="development", input_schema={"path": "workspace-relative path"}),
    _cap("workspace.command", "Run workspace command", "Run an argv-only command allowed by the workspace command policy.", zone="worker", effect="execute", risk="high", category="development", input_schema={"argv": "list of strings"}),
    _cap("workspace.test", "Run workspace tests", "Run a configured test command in the issued workspace.", zone="worker", effect="execute", risk="medium", category="development", input_schema={"argv": "list of strings"}),
    _cap("workspace.git_status", "Read local git status", "Read git status for the isolated worktree.", zone="worker", effect="read", category="development"),
    _cap("workspace.git_diff", "Read local git diff", "Read the current isolated worktree diff.", zone="worker", effect="read", category="development"),
    _cap("gmail.read_email", "Read email", "Search and read Gmail messages and threads.", zone="broker", effect="read", network=True, credentials=True, connection=True, provider="Google", category="communication", assistant=True),
    _cap("gmail.create_draft", "Create drafts", "Create reviewable Gmail drafts without sending.", zone="broker", effect="create", risk="medium", network=True, credentials=True, connection=True, provider="Google", category="communication", assistant=True),
    _cap("gmail.send_email", "Send email", "Send or reply to Gmail messages.", zone="broker", effect="mutate", risk="high", network=True, credentials=True, connection=True, confirmation=True, provider="Google", category="communication", assistant=True),
    _cap("gmail.delete_email", "Delete email", "Move Gmail messages to Trash.", zone="broker", effect="delete", risk="high", network=True, credentials=True, connection=True, confirmation=True, destructive=True, provider="Google", category="communication", assistant=True),
    _cap("calendar.read_availability", "Read availability", "Read calendar events in an exact ISO-8601 time range.", zone="broker", effect="read", network=True, credentials=True, connection=True, provider="Google", category="productivity", assistant=True, hermes=True, input_schema={"start_time": "ISO 8601 datetime", "end_time": "ISO 8601 datetime", "timezone": "IANA timezone"}),
    _cap("calendar.create_event", "Create events", "Create a calendar event with explicit time and timezone.", zone="broker", effect="create", risk="medium", network=True, credentials=True, connection=True, confirmation=True, provider="Google", category="productivity", assistant=True, hermes=True, input_schema={"title": "string", "start_time": "ISO 8601 datetime", "end_time": "ISO 8601 datetime", "timezone": "IANA timezone", "attendees": "list of email addresses", "location": "string", "description": "string", "reminder_minutes": "integer 0..40320"}),
    _cap("calendar.delete_event", "Delete events", "Delete calendar events.", zone="broker", effect="delete", risk="high", network=True, credentials=True, connection=True, confirmation=True, destructive=True, provider="Google", category="productivity", assistant=True),
    _cap("contacts.search_contacts", "Search contacts", "Search Google Contacts.", zone="broker", effect="read", network=True, credentials=True, connection=True, provider="Google", category="productivity", assistant=True),
    _cap("contacts.resolve_recipient", "Resolve recipients", "Resolve saved contact details for another governed action.", zone="broker", effect="read", risk="medium", network=True, credentials=True, connection=True, provider="Google", category="productivity", assistant=True),
    _cap("github.read_repo", "Read repositories", "Read repository metadata, files, pull requests, and checks.", zone="broker", effect="read", network=True, credentials=True, connection=True, provider="GitHub", category="development", assistant=True),
    _cap("github.create_branch", "Create branches", "Create GitHub branches for prepared changes.", zone="broker", effect="create", risk="medium", network=True, credentials=True, connection=True, provider="GitHub", category="development", assistant=True),
    _cap("github.create_pr", "Open pull requests", "Open pull requests from prepared branch changes.", zone="broker", effect="create", risk="medium", network=True, credentials=True, connection=True, provider="GitHub", category="development", assistant=True),
    _cap("github.merge_pr", "Merge pull requests", "Merge pull requests after required checks pass.", zone="broker", effect="mutate", risk="high", network=True, credentials=True, connection=True, confirmation=True, provider="GitHub", category="development", assistant=True),
    _cap("kasa.discover_devices", "Discover Kasa devices", "Discover supported TP-Link Kasa devices.", zone="broker", effect="read", network=True, connection=True, provider="TP-Link", category="smart-home", assistant=True, hermes=True, aliases=("kasa_discover_devices",)),
    _cap("kasa.get_state", "Read plug state", "Read the verified state of a selected Kasa device.", zone="broker", effect="read", network=True, connection=True, provider="TP-Link", category="smart-home", assistant=True, hermes=True, input_schema={"target": "string alias, host, or device id; optional when exactly one device exists"}, aliases=("kasa_get_state",)),
    _cap("kasa.turn_on", "Turn on plug", "Turn on one selected Kasa plug and verify its state.", zone="broker", effect="mutate", risk="medium", network=True, connection=True, confirmation=True, approval="always_ask", provider="TP-Link", category="smart-home", assistant=True, hermes=True, input_schema={"target": "string alias, host, or device id"}, aliases=("kasa_turn_on",)),
    _cap("kasa.turn_off", "Turn off plug", "Turn off one selected Kasa plug and verify its state.", zone="broker", effect="mutate", risk="medium", network=True, connection=True, confirmation=True, approval="always_ask", provider="TP-Link", category="smart-home", assistant=True, hermes=True, input_schema={"target": "string alias, host, or device id"}, aliases=("kasa_turn_off",)),
    _cap("house.get_status", "Read house status", "Read the current Omnix house status.", zone="context", effect="read", category="smart-home", hermes=True, aliases=("get_house_status",)),
    _cap("hermes.get_status", "Read Hermes status", "Read Hermes runtime status.", zone="context", effect="read", category="platform", hermes=True, aliases=("get_hermes_status",)),
    _cap("hermes.get_diagnostics_schema", "Read Hermes diagnostics schema", "Read Hermes diagnostics schema.", zone="context", effect="read", category="platform", hermes=True, aliases=("get_hermes_diagnostics_schema",)),
)


def default_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry(_DEFAULT_CAPABILITIES)
