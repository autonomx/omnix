"""Several characters in one call (companion 5): who speaks, and the session as the speaker sees it.

A character chat's own character is the scene's host. The person may add up to four guests (chat's
``omnix_chat_scene_members``). Each reply is spoken by one of them, and its metadata names the speaker;
a reply without a speaker is the host's, so every older reply stays the host's.

A guest's reply is generated from ``speaking_as(session, guest)``: a copy of the session whose identity
is the guest's, so its persona, grants, memory scope and voice are the guest's own and never the host's.
The view is read-only. Every save path refuses it (``refuse_scene_view``), because saving it would move the
chat to the guest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SPEAKER_ID_KEY = "speaker_character_id"
SPEAKER_NAME_KEY = "speaker_name"
MAX_SCENE_GUESTS = 4
# Message metadata memory reads (companion 6.3, 6.5): the part of an interrupted scene line the person heard, as
# words (None when unknown), and a person's turn that mostly repeats a character's line the microphone heard.
HEARD_TEXT_KEY = "heard_text"
SUSPECTED_ECHO_KEY = "suspected_echo"


class SceneViewSaveError(RuntimeError):
    """A speaker's view of a session was about to be saved as the session."""


@dataclass(frozen=True)
class SceneMember:
    """A character on the call. ``summary`` is a one-line, untrusted description of who they are (Q20)."""

    character_id: str
    display_name: str
    summary: str = field(default="", compare=False)


@dataclass(frozen=True)
class Scene:
    """Who is in the call: the host first, then the guests in seat order, and who speaks this reply."""

    host: SceneMember
    guests: tuple[SceneMember, ...]
    speaker_id: str

    @property
    def members(self) -> tuple[SceneMember, ...]:
        return (self.host, *self.guests)

    @property
    def speaker(self) -> SceneMember:
        return next((member for member in self.members if member.character_id == self.speaker_id), self.host)

    def name_of(self, character_id: str | None) -> str:
        wanted = character_id or self.host.character_id
        return next((member.display_name for member in self.members if member.character_id == wanted), "")

    def with_speaker(self, character_id: str) -> Scene:
        if character_id not in {member.character_id for member in self.members}:
            raise ValueError(f"{character_id!r} is not in this scene")
        return Scene(host=self.host, guests=self.guests, speaker_id=character_id)


def scene_of(session: Any) -> Scene | None:
    """The scene a session (or a speaker's view of it) carries; ``None`` outside a scene."""
    private = getattr(session, "__pydantic_private__", None) or {}
    scene = private.get("_scene")
    return scene if isinstance(scene, Scene) else None


def with_scene(session: Any, scene: Scene | None) -> Any:
    """A copy of the session carrying ``scene`` for this turn (``None`` or no guests: the session itself).

    A copy, so a session a store keeps in memory never carries one turn's scene into the next.
    """
    if scene is None or not scene.guests:
        return session
    view = session.model_copy()
    view._scene = scene
    return view


def speaker_of(message: Any, host_character_id: str | None) -> str | None:
    """Who spoke an assistant message: its recorded speaker, else the host."""
    metadata = getattr(message, "metadata", None) or {}
    speaker = str(metadata.get(SPEAKER_ID_KEY) or "").strip()
    return speaker or host_character_id


def speaking_as(session: Any, scene: Scene) -> Any:
    """The session as ``scene.speaker`` sees it: the speaker's identity, the host's transcript.

    For the host this is a copy of the session with the scene attached. For a guest it is a copy whose
    character is the guest's, with no voice override, profile pin or identity hash of the host's (the
    guest's are resolved from its own profile), and without the host's memory snapshot.
    """
    if scene.speaker_id == scene.host.character_id:
        return with_scene(session, scene)
    view = session.model_copy(update={
        "character_id": scene.speaker_id,
        "voice_asset_id": None,
        "character_profile_version": None,
        "effective_identity_hash": None,
        "memory_snapshot_id": None,
        "memory_snapshot_revision": None,
        "memory_record_count": 0,
        "memory_last_refreshed_at": None,
    })
    view._scene = scene
    view._scene_view = True
    return view


def answered_by_view(session: Any, user_message_id: str) -> Any:
    """The session as the member who answered a person's turn sees it (whose memory the turn feeds).

    A turn the host answered, or one outside a character chat, gives the session itself; a guest's gives a
    read-only view with the guest's character, like ``speaking_as``.
    """
    host = getattr(session, "character_id", None)
    if getattr(session, "interaction_mode", "system") != "character" or not host:
        return session
    reply = next(
        (message for message in getattr(session, "messages", ())
         if message.role == "assistant" and (message.metadata or {}).get("reply_to_message_id") == user_message_id),
        None,
    )
    speaker = speaker_of(reply, host) if reply is not None else host
    if speaker == host:
        return session
    view = session.model_copy(update={
        "character_id": speaker,
        "memory_snapshot_id": None,
        "memory_snapshot_revision": None,
        "memory_record_count": 0,
        "memory_last_refreshed_at": None,
    })
    view._scene_view = True
    return view


def is_scene_view(session: Any) -> bool:
    private = getattr(session, "__pydantic_private__", None) or {}
    return bool(private.get("_scene_view"))


def refuse_scene_view(session: Any) -> None:
    """Every save path calls this: a speaker's view is never saved as the session."""
    if is_scene_view(session):
        raise SceneViewSaveError(f"a scene speaker's view of chat {getattr(session, 'id', '?')} cannot be saved")


__all__ = [
    "HEARD_TEXT_KEY",
    "MAX_SCENE_GUESTS",
    "SUSPECTED_ECHO_KEY",
    "SPEAKER_ID_KEY",
    "SPEAKER_NAME_KEY",
    "Scene",
    "SceneMember",
    "SceneViewSaveError",
    "answered_by_view",
    "is_scene_view",
    "refuse_scene_view",
    "scene_of",
    "speaker_of",
    "speaking_as",
    "with_scene",
]
