"""A voice client credential, as the client facade passes it around."""
from __future__ import annotations

from typing import TypedDict


class VoiceClientCredential(TypedDict, total=False):
    id: str
    name: str
    workspace_id: str
    owner_user_id: str
    capabilities: frozenset[str]
