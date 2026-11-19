"""The capabilities a call may ask for by voice, each with a typed input, and the check before anything is recorded.

A call's model proposes an action as ``[[do: <capability> <json input> || words to say]]`` (``live_voice.llm.call_tools``).
Nothing in that line is trusted: the capability must be one offered here, in a group the speaker holds
(``owner_grants``), and the input must parse into the capability's model with its strings bounded. The registry's
``input_schema`` is prose, so the types live here. A write is never run from a call's request: it becomes a proposal
the person confirms (``chat.live_call_actions``).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

SMART_HOME = "smart_home"
CALENDAR = "calendar"
ACTION_ABILITIES = frozenset({SMART_HOME, CALENDAR})

Effect = Literal["read", "write"]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ListDevicesInput(_Input):
    pass


class DeviceInput(_Input):
    target: str = Field(min_length=1, max_length=80)


class SetDeviceInput(DeviceInput):
    on: StrictBool


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed


class _TimeRange(_Input):
    start_time: str = Field(min_length=10, max_length=40)
    end_time: str = Field(min_length=10, max_length=40)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _real_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be an IANA name") from exc
        return value

    @model_validator(mode="after")
    def _ordered(self) -> _TimeRange:
        try:
            start, end = _instant(self.start_time), _instant(self.end_time)
        except ValueError as exc:
            raise ValueError("times must be ISO 8601") from exc
        zone = ZoneInfo(self.timezone)
        start = start if start.tzinfo else start.replace(tzinfo=zone)
        end = end if end.tzinfo else end.replace(tzinfo=zone)
        if end <= start:
            raise ValueError("the end must be after the start")
        return self


class AvailabilityInput(_TimeRange):
    pass


class CreateEventInput(_TimeRange):
    title: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    reminder_minutes: int | None = Field(default=None, ge=0, le=40320)


@dataclass(frozen=True)
class VoiceAction:
    capability: str
    ability: str
    effect: Effect
    summary: str
    model: type[_Input]


# Offered by voice. Not offered: kasa.* (the plugs are reached through home.*, one path per device), home.get_energy
# (always "not supported"), home.apply_scene (a list of actions), calendar attendees and calendar.delete_event.
VOICE_ACTIONS: dict[str, VoiceAction] = {action.capability: action for action in (
    VoiceAction("calendar.create_event", CALENDAR, "write", "add an event to their calendar", CreateEventInput),
    VoiceAction("calendar.read_availability", CALENDAR, "read", "read their calendar in a time range",
                AvailabilityInput),
    VoiceAction("home.get_state", SMART_HOME, "read", "check whether a device is on", DeviceInput),
    VoiceAction("home.list_devices", SMART_HOME, "read", "list their home devices", ListDevicesInput),
    VoiceAction("home.set_state", SMART_HOME, "write", "turn a device on or off", SetDeviceInput),
)}
# The read that shows whether an ability's tool is enabled and connected.
_PROBES = {SMART_HOME: "home.list_devices", CALENDAR: "calendar.read_availability"}


@dataclass(frozen=True)
class VoiceActionCheck:
    ok: bool
    reason: str
    ability: str = ""
    capability: str = ""
    effect: Effect | None = None
    input: dict[str, Any] | None = None


def _canonical(capability: str) -> str | None:
    from app.capabilities.registry import default_capability_registry

    registry = default_capability_registry()
    canonical = registry.canonical_id(capability)
    row = registry.get(canonical) if canonical else None
    return canonical if row is not None and row.assistant_visible else None


def action_ability(capability: str) -> str:
    """The ability a capability id belongs to, or "" when the call does not offer it."""
    action = VOICE_ACTIONS.get(_canonical(capability.strip()) or "")
    return action.ability if action is not None else ""


def check_voice_action(capability: str, raw_input: Any, grants: dict[str, bool]) -> VoiceActionCheck:
    """Whether a proposed action may be recorded: an offered capability, in a granted group, with a typed input."""
    canonical = _canonical(str(capability or "").strip())
    action = VOICE_ACTIONS.get(canonical or "")
    if action is None:
        return VoiceActionCheck(False, "invalid")
    if not grants.get(action.ability):
        return VoiceActionCheck(False, "not_granted", ability=action.ability, capability=action.capability)
    if not isinstance(raw_input, dict):
        return VoiceActionCheck(False, "invalid", ability=action.ability, capability=action.capability)
    try:
        parsed = action.model.model_validate(raw_input)
    except ValidationError:
        return VoiceActionCheck(False, "invalid", ability=action.ability, capability=action.capability)
    return VoiceActionCheck(True, "granted", ability=action.ability, capability=action.capability,
                            effect=action.effect, input=parsed.model_dump(mode="json", exclude_none=True))


def describe_voice_action(capability: str, data: dict[str, Any]) -> str:
    """A short, code-built line for what an action is, as the call's task list shows it."""
    target = " ".join(str(data.get("target") or "").split())[:80]
    if capability == "home.set_state":
        return f"turn {'on' if data.get('on') else 'off'} {target}"
    if capability == "home.get_state":
        return f"check {target}"
    if capability == "home.list_devices":
        return "list home devices"
    if capability == "calendar.read_availability":
        return f"check the calendar {data.get('start_time', '')} to {data.get('end_time', '')}"
    if capability == "calendar.create_event":
        return f"add ‘{' '.join(str(data.get('title') or '').split())[:80]}’ to the calendar"
    return capability


def voice_action_catalog(abilities: dict[str, bool], context: dict[str, str] | None = None) -> str | None:
    """The actions a call may ask for now, sorted, with their inputs; None when none is offered."""
    rows = [action for capability, action in sorted(VOICE_ACTIONS.items()) if abilities.get(action.ability)]
    if not rows:
        return None
    lines = ["Actions you can ask for now (id: what it does; its input):"]
    for action in rows:
        fields = []
        for name, info in action.model.model_fields.items():
            kind = "true or false" if name == "on" else "integer" if name == "reminder_minutes" else "text"
            if name in {"start_time", "end_time"}:
                kind = "ISO 8601 date-time"
            elif name == "timezone":
                kind = "IANA timezone"
            fields.append(f"\"{name}\": {kind}{'' if info.is_required() else ', optional'}")
        lines.append(f"- {action.capability}: {action.summary}; {{{', '.join(fields)}}}")
    if context:
        now, zone = context.get("current_datetime"), context.get("user_timezone")
        if now:
            lines.append(f"It is now {now}" + (f", and their timezone is {zone}." if zone else "."))
        rule = context.get("calendar_rule")
        if rule and abilities.get(CALENDAR):
            lines.append(rule)
    return "\n".join(lines)


_AVAILABILITY_SECONDS = 60.0
_MAX_AVAILABILITY_ENTRIES = 16  # one per action ability
_availability: dict[str, tuple[float, bool]] = {}


def voice_action_ability_available(ability: str) -> bool:
    """Whether an action ability's tool is enabled and connected now; kept a minute.

    A call offers an action only when it could run: one that cannot would be a promise the call never keeps.
    """
    probe = _PROBES.get(ability)
    if probe is None:
        return False
    now = time.monotonic()
    cached = _availability.get(ability)
    if cached is not None and now - cached[0] < _AVAILABILITY_SECONDS:
        return cached[1]
    from .gate import review_assistant_tool_request
    from .models import AssistantToolRequest

    available = False
    try:
        decision = review_assistant_tool_request(
            AssistantToolRequest(tool_id=probe.split(".", 1)[0], action_id=probe))
        available = bool(decision.allowed)
    except Exception:  # noqa: BLE001 - not offered, not broken
        logger.warning("voice actions: availability of %s could not be read", ability, exc_info=True)
    if len(_availability) >= _MAX_AVAILABILITY_ENTRIES:
        _availability.clear()
    _availability[ability] = (now, available)
    return available


def reset_voice_action_availability() -> None:
    _availability.clear()


class AssistantCallActions:
    """Chat's ``CHAT_CALL_ACTIONS`` port: what a live call's action task needs, so chat never imports these tools."""

    def check(self, capability: str, data: Any) -> VoiceActionCheck:
        # The speaker's grant was checked when the ask was recorded; here only the input is parsed again.
        return check_voice_action(capability, data, {action_ability(capability): True})

    def describe(self, capability: str, data: dict[str, Any]) -> str:
        return describe_voice_action(capability, data)

    def tool_request(self, *, session_id: str, task_id: str, capability: str, data: dict[str, Any]) -> Any:
        from .models import AssistantToolRequest

        return AssistantToolRequest(tool_id=capability.split(".", 1)[0], action_id=capability,
                                    session_id=session_id, proposal_id=task_id, input=data)

    def review(self, request: Any, *, approved: bool, policy_floor: str) -> Any:
        from .gate import review_assistant_tool_request

        return review_assistant_tool_request(request, approved=approved, policy_floor=policy_floor)

    def call_owner(self, session: Any) -> str:
        from .owner_grants import SYSTEM_OWNER_ID

        if str(getattr(session, "interaction_mode", "") or "") == "character":
            return str(getattr(session, "character_id", "") or "")
        return SYSTEM_OWNER_ID

    def granted(self, owner_id: str, *, ability: str = "", capability: str = "") -> bool:
        # Read again when a call's task starts and when its proposal is confirmed, so a revoked grant stops it.
        from .owner_grants import authorize

        wanted = action_ability(capability) if capability else ability
        if not owner_id or not wanted:
            return False
        try:
            return authorize(owner_id, wanted).allowed
        except Exception:  # noqa: BLE001 - unreadable grants allow nothing
            logger.warning("call actions: the grants of %s could not be read", owner_id, exc_info=True)
            return False


__all__ = [
    "ACTION_ABILITIES", "AssistantCallActions", "CALENDAR", "SMART_HOME", "VOICE_ACTIONS", "VoiceAction",
    "VoiceActionCheck",
    "action_ability", "check_voice_action", "describe_voice_action", "reset_voice_action_availability",
    "voice_action_ability_available", "voice_action_catalog",
]
