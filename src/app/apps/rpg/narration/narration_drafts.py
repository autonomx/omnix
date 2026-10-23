"""Live drafts of a turn's narration while the model writes it.

A foreground turn opens a draft for its submission; the narrative writer
publishes the prose it has so far, and the play screen polls it so the first
sentences appear while the rest is still being written. A draft is display only:
it is never game state, it lives in this process's memory for minutes, and the
turn's validated narration replaces it. Drafts are scoped to the user and
workspace that submitted the turn.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

_TTL_SECONDS = 600.0
_MAX_DRAFTS = 256

DraftKey = tuple[str, str, str, str]  # user, workspace, session, submission


@dataclass
class _Draft:
    text: str = ""
    done: bool = False
    updated: float = 0.0


_DRAFTS: dict[DraftKey, _Draft] = {}
_LOCK = threading.Lock()
_CURRENT: ContextVar[DraftKey | None] = ContextVar("RPG_NARRATION_DRAFT", default=None)


def _key(session_id: str, submission_id: str) -> DraftKey | None:
    from app.runtime.tenant_context import current_tenant

    try:
        tenant = current_tenant()
    except RuntimeError:
        return None
    if not session_id or not submission_id:
        return None
    return (tenant.user_id, tenant.workspace_id, session_id, submission_id)


def _prune(now: float) -> None:
    for key in [key for key, draft in _DRAFTS.items() if now - draft.updated > _TTL_SECONDS]:
        _DRAFTS.pop(key, None)
    while len(_DRAFTS) > _MAX_DRAFTS:
        _DRAFTS.pop(min(_DRAFTS, key=lambda key: _DRAFTS[key].updated), None)


@contextmanager
def narration_draft_context(session_id: str, submission_id: str) -> Iterator[None]:
    """Open this turn's draft; the narrative writer publishes into it while the context is active."""
    key = _key(session_id, submission_id)
    if key is None:
        yield
        return
    now = time.monotonic()
    with _LOCK:
        _prune(now)
        _DRAFTS[key] = _Draft(updated=now)
    token = _CURRENT.set(key)
    try:
        yield
    finally:
        _CURRENT.reset(token)
        with _LOCK:
            draft = _DRAFTS.get(key)
            if draft is not None:
                draft.done = True
                draft.updated = time.monotonic()


def narration_draft_active() -> bool:
    return _CURRENT.get() is not None


def publish_narration_draft(text: str) -> None:
    key = _CURRENT.get()
    if key is None:
        return
    with _LOCK:
        draft = _DRAFTS.get(key)
        if draft is not None and text != draft.text:
            draft.text = text
            draft.updated = time.monotonic()


def read_narration_draft(session_id: str, submission_id: str) -> dict[str, object]:
    """The current user's draft for this submission (empty when there is none)."""
    key = _key(session_id, submission_id)
    with _LOCK:
        draft = _DRAFTS.get(key) if key is not None else None
        if draft is None:
            return {"text": "", "done": False, "found": False}
        return {"text": draft.text, "done": draft.done, "found": True}


def _read_string(buffer: str, index: int) -> tuple[str, int, bool]:
    """Decode the JSON string starting after its opening quote, as far as it has arrived."""
    chars: list[str] = []
    while index < len(buffer):
        char = buffer[index]
        if char == '"':
            return "".join(chars), index + 1, True
        if char == "\\":
            size = 6 if buffer[index + 1:index + 2] == "u" else 2
            escape = buffer[index:index + size]
            if len(escape) < size:
                break  # the escape is still arriving
            try:
                chars.append(json.loads(f'"{escape}"'))
            except ValueError:
                pass
            index += size
            continue
        chars.append(char)
        index += 1
    return "".join(chars), len(buffer), False


# A block's own ``text``: the outer object, its ``blocks`` array, then the block object.
_BLOCK_DEPTH = ["{", "[", "{"]


def draft_text_from_partial_json(buffer: str) -> str:
    """The prose of the narrative blocks in a partly written ``{"blocks": [{"text": ...}]}`` answer.

    Only each block's own ``text`` counts (not its claims'); a block's text is
    decoded as far as it has arrived, and blocks are joined by blank lines.
    """
    texts: list[str] = []
    stack: list[str] = []
    key = ""
    expecting_value = False
    index = 0
    while index < len(buffer):
        char = buffer[index]
        if char == '"':
            value, index, complete = _read_string(buffer, index + 1)
            if expecting_value:
                if key == "text" and stack == _BLOCK_DEPTH and value.strip():
                    texts.append(value.strip())
                expecting_value = False
            elif stack and stack[-1] == "{":
                key = value
            if not complete:
                break
            continue
        if char in "{[":
            stack.append(char)
            expecting_value = False
        elif char in "}]":
            if stack:
                stack.pop()
        elif char == ":":
            expecting_value = True
        elif char == ",":
            key, expecting_value = "", False
        index += 1
    return "\n\n".join(texts)


__all__ = [
    "draft_text_from_partial_json",
    "narration_draft_active",
    "narration_draft_context",
    "publish_narration_draft",
    "read_narration_draft",
]
