"""First-class conversational objective continuity for Omnix routing.

ActiveObjective is reference state, not execution authority. It survives ordinary
chat turns so terse follow-ups can be interpreted semantically without replaying
an unlimited transcript or relying on regexes to choose an execution lane.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ObjectiveStatus = Literal[
    "active",
    "blocked",
    "awaiting_user",
    "completed",
    "abandoned",
    "cancelled",
]


class ActiveObjective(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_id: str = Field(min_length=1, max_length=160)
    objective_type: str = Field(min_length=1, max_length=80)
    canonical_request: str = Field(min_length=1)
    status: ObjectiveStatus = "active"
    blocking_reason: str | None = Field(default=None, max_length=1000)
    workspace_name: str | None = Field(default=None, max_length=240)
    originating_turn_id: str | None = Field(default=None, max_length=240)
    last_relevant_turn_id: str | None = Field(default=None, max_length=240)
    run_id: str | None = Field(default=None, max_length=240)
    profile: str | None = Field(default=None, max_length=80)

    def reference_text(self, *, max_request_chars: int = 8000) -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        request = self.canonical_request
        if len(request) > max_request_chars:
            # Keep the full user-authored request in persisted objective state for
            # exact replay, but bound the semantic-routing projection. Preserve
            # both ends plus a digest so the classifier can identify the task
            # without paying to resend an unbounded prompt on every turn.
            head_chars = max_request_chars * 3 // 4
            tail_chars = max_request_chars - head_chars
            payload["canonical_request"] = (
                request[:head_chars]
                + "\n...[objective text omitted from routing projection]...\n"
                + request[-tail_chars:]
            )
            payload["canonical_request_digest"] = hashlib.sha256(
                request.encode("utf-8")
            ).hexdigest()
            payload["canonical_request_truncated_for_routing"] = True
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class RoutingEnvironment(BaseModel):
    """Current-turn environment facts supplied to semantic routing.

    These facts can resolve statements such as "I attached the folder now", but
    they never grant execution authority by themselves.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_workspace: str | None = Field(default=None, max_length=240)
    workspace_source: Literal["turn_attachment", "configured_default", "none"] = "none"
    workspace_attached_this_turn: bool = False
    attachment_kinds: list[str] = Field(default_factory=list, max_length=12)
    attachment_count: int = Field(default=0, ge=0, le=100)
    agent_mode_selected: bool = False


_WORKSPACE_UNAVAILABLE = re.compile(
    r"(?:don'?t have access to the project folder|coding workspace.*(?:not available|only the image)|"
    r"workspace editor.*(?:not available|unavailable)|no coding workspace is configured)",
    re.I,
)
_STRONG_CONTINUITY = re.compile(
    r"\b(?:again|retry|re-?try|continue|resume|previous|before|same\s+(?:thing|task|change)|"
    r"attached|include(?:d)?\s+(?:the\s+)?(?:folder|workspace|project))\b",
    re.I,
)
_TERSE_REFERENCE = re.compile(
    r"^(?:please\s+)?(?:do|fix|change|update|run|try)\s+(?:it|that|this)(?:\s+again)?[.!\s]*$",
    re.I,
)


def _workspace_name(value: str | None) -> str | None:
    text = str(value or "").strip().rstrip("\\/")
    if not text:
        return None
    return re.split(r"[\\/]", text)[-1] or None


def build_routing_environment(user_message: Any) -> RoutingEnvironment:
    metadata = getattr(user_message, "metadata", {}) or {}
    selected = str(metadata.get("workspace_root") or "").strip()
    configured = str(os.environ.get("OMNIX_AGENT_DEFAULT_REPOSITORY", "") or "").strip()
    if selected:
        workspace = _workspace_name(selected)
        source = "turn_attachment"
    elif configured:
        workspace = _workspace_name(configured)
        source = "configured_default"
    else:
        workspace = None
        source = "none"

    kinds: list[str] = []
    if selected:
        kinds.append("local_folder")
    if isinstance(metadata.get("image_data_url"), str) and metadata.get("image_data_url"):
        kinds.append("image")
    raw_attachments = metadata.get("attachments")
    attachment_count = len(raw_attachments) if isinstance(raw_attachments, list) else 0
    if attachment_count:
        kinds.append("file")

    return RoutingEnvironment(
        active_workspace=workspace,
        workspace_source=source,
        workspace_attached_this_turn=bool(selected),
        attachment_kinds=list(dict.fromkeys(kinds)),
        attachment_count=attachment_count,
        agent_mode_selected=bool(metadata.get("agent_mode")),
    )


def make_active_objective(
    *,
    canonical_request: str,
    profile: str,
    status: ObjectiveStatus,
    blocking_reason: str | None = None,
    workspace_name: str | None = None,
    originating_turn_id: str | None = None,
    last_relevant_turn_id: str | None = None,
    run_id: str | None = None,
) -> ActiveObjective:
    request = str(canonical_request or "").strip()
    profile_id = str(profile or "unknown").strip() or "unknown"
    origin = str(originating_turn_id or "").strip() or None
    run = str(run_id or "").strip() or None
    if run:
        objective_id = f"run:{run}"
    else:
        digest = hashlib.sha256(
            f"{origin or ''}\n{profile_id}\n{request}".encode("utf-8")
        ).hexdigest()[:24]
        objective_id = f"chat-objective:{digest}"
    return ActiveObjective(
        objective_id=objective_id,
        objective_type=profile_id,
        canonical_request=request,
        status=status,
        blocking_reason=(str(blocking_reason).strip()[:1000] if blocking_reason else None),
        workspace_name=workspace_name,
        originating_turn_id=origin,
        last_relevant_turn_id=(
            str(last_relevant_turn_id or "").strip() or origin
        ),
        run_id=run,
        profile=profile_id,
    )


def _objective_from_message(messages: list[Any], index: int) -> ActiveObjective | None:
    message = messages[index]
    metadata = getattr(message, "metadata", {}) or {}

    explicit = metadata.get("active_objective")
    raw_run = metadata.get("agent_run")

    # A terminal run snapshot is newer and more authoritative state than a
    # carried-forward objective reference on the same message. Evaluate run
    # status first so completed/cancelled work cannot be resurrected by stale
    # metadata.
    if getattr(message, "role", None) == "assistant" and isinstance(raw_run, dict):
        task = str(raw_run.get("task") or "").strip()
        profile = str(raw_run.get("profile") or "").strip()
        raw_status = str(raw_run.get("status") or "").strip().casefold()
        if task and profile:
            if raw_status in {"completed"}:
                status: ObjectiveStatus = "completed"
            elif raw_status in {"cancelled", "canceled"}:
                status = "cancelled"
            elif raw_status in {"waiting_for_approval", "paused"}:
                status = "awaiting_user"
            elif raw_status in {"failed", "rejected"}:
                status = "blocked"
            else:
                status = "active"
            start = metadata.get("agent_start")
            reason = None
            if isinstance(start, dict):
                reason = str(start.get("reason") or start.get("error") or "").strip() or None
            if reason is None:
                reason = str(raw_run.get("last_error") or "").strip() or None
            source = messages[index - 1] if index > 0 else None
            source_meta = getattr(source, "metadata", {}) or {}
            return make_active_objective(
                canonical_request=task,
                profile=profile,
                status=status,
                blocking_reason=reason,
                workspace_name=_workspace_name(source_meta.get("workspace_root")),
                originating_turn_id=(
                    str(getattr(source, "id", "") or "").strip() or None
                    if getattr(source, "role", None) == "user"
                    else None
                ),
                last_relevant_turn_id=str(getattr(message, "id", "") or "").strip() or None,
                run_id=str(raw_run.get("run_id") or "").strip() or None,
            )

    if isinstance(explicit, dict):
        try:
            return ActiveObjective.model_validate(explicit)
        except Exception:
            pass

    if getattr(message, "role", None) != "assistant":
        return None

    if _WORKSPACE_UNAVAILABLE.search(str(getattr(message, "content", "") or "")):
        source = messages[index - 1] if index > 0 else None
        if getattr(source, "role", None) == "user":
            task = str(getattr(source, "content", "") or "").strip()
            if task:
                source_meta = getattr(source, "metadata", {}) or {}
                return make_active_objective(
                    canonical_request=task,
                    profile="coding",
                    status="blocked",
                    blocking_reason="workspace_required",
                    workspace_name=_workspace_name(source_meta.get("workspace_root")),
                    originating_turn_id=str(getattr(source, "id", "") or "").strip() or None,
                    last_relevant_turn_id=str(getattr(message, "id", "") or "").strip() or None,
                )
    return None


def resolve_active_objective(session: Any, user_message: Any) -> ActiveObjective | None:
    """Resolve the newest persisted objective without treating it as authority."""

    current_id = str(getattr(user_message, "id", "") or "").strip()
    messages = list(getattr(session, "messages", []) or [])
    for index in range(len(messages) - 1, -1, -1):
        candidate = messages[index]
        if current_id and str(getattr(candidate, "id", "") or "").strip() == current_id:
            continue
        objective = _objective_from_message(messages, index)
        if objective is None:
            continue
        if objective.status in {"completed", "abandoned", "cancelled"}:
            return None
        return objective
    return None


def objective_continuity_candidate(content: str) -> bool:
    """Detect only that semantic context is required; never choose a lane."""

    text = " ".join(str(content or "").strip().split())
    if not text:
        return False
    if _STRONG_CONTINUITY.search(text):
        return True
    if _TERSE_REFERENCE.fullmatch(text):
        return True
    words = text.split()
    return len(words) <= 8 and bool(
        re.search(r"\b(?:it|that|this|same|too)\b", text, re.I)
    )


__all__ = [
    "ActiveObjective",
    "RoutingEnvironment",
    "build_routing_environment",
    "make_active_objective",
    "objective_continuity_candidate",
    "resolve_active_objective",
]
