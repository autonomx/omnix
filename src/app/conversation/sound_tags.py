"""Sound tags in a live call's reply.

A live character may open a sentence with ``[hmm]``, ``[chuckle]`` or ``[sigh]``. The browser plays the
voice's own recorded clip for the tag and never sends the tag to speech; the saved reply keeps the words
only, with the tags and their places in its metadata. Any other bracketed text is stage direction the
voice must not read, so it is removed too.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

# Tag name -> the cue clip it plays (``voice_cues/<voice>/<cue>-vN.wav``).
SOUND_TAG_CUES: dict[str, str] = {
    "hmm": "hmm",
    "chuckle": "amused_exhale",
    "sigh": "sigh",
}

_MAX_GROUP_CHARS = 80
_GROUP = re.compile(r"\[([^\[\]\n]{0,%d})\]" % _MAX_GROUP_CHARS)
_KNOWN = (
    ("hmm", re.compile(r"h+m+", re.IGNORECASE)),
    ("chuckle", re.compile(r"(?:chuckle|laugh|giggle)s?", re.IGNORECASE)),
    ("sigh", re.compile(r"sighs?", re.IGNORECASE)),
)
_PUNCTUATION = frozenset(",.;:!?")
_MARK_BASE = 0xE000
_MARK_TAGS = tuple(SOUND_TAG_CUES)


@dataclass(frozen=True)
class SoundTag:
    tag: str
    at: int  # character offset in the cleaned text where the sound plays

    @property
    def cue_id(self) -> str:
        return SOUND_TAG_CUES[self.tag]


def sound_tag_name(inner: str) -> str | None:
    """The tag a bracket group's inside names, or None for any other bracketed text."""
    word = inner.strip()
    for tag, pattern in _KNOWN:
        if pattern.fullmatch(word):
            return tag
    return None


def split_sound_tags(text: str) -> tuple[str, tuple[SoundTag, ...]]:
    """Remove every bracket group and stray bracket; return the words and the known tags with their places."""
    if not text or ("[" not in text and "]" not in text):
        return text, ()

    def mark(match: re.Match[str]) -> str:
        tag = sound_tag_name(match.group(1))
        return f" {chr(_MARK_BASE + _MARK_TAGS.index(tag))} " if tag else " "

    working = _GROUP.sub(mark, text).replace("[", " ").replace("]", " ")
    out: list[str] = []
    tags: list[SoundTag] = []
    for char in working:
        code = ord(char)
        if _MARK_BASE <= code < _MARK_BASE + len(_MARK_TAGS):
            tags.append(SoundTag(_MARK_TAGS[code - _MARK_BASE], len(out)))
            continue
        if char.isspace():
            if out and out[-1] != " ":
                out.append(" ")
            continue
        if char in _PUNCTUATION and out and out[-1] == " ":
            out.pop()
            tags = [SoundTag(tag.tag, min(tag.at, len(out))) for tag in tags]
        out.append(char)
    cleaned = "".join(out).rstrip()
    return cleaned, tuple(SoundTag(tag.tag, min(tag.at, len(cleaned))) for tag in tags)


def strip_sound_tags(text: str) -> str:
    return split_sound_tags(text)[0]


def strip_sound_tags_from_stream(events: Iterable[Any]) -> Iterator[Any]:
    """Pass a reply stream through, saving the finished reply without tags and recording them in its metadata."""
    try:
        for event in events:
            if isinstance(event, dict) and event.get("type") == "complete":
                event = _clean_complete_event(event)
            yield event
    finally:
        close = getattr(events, "close", None)
        if callable(close):
            close()


def _clean_complete_event(event: dict[str, Any]) -> dict[str, Any]:
    content = event.get("content")
    if not isinstance(content, str):
        return event
    cleaned, tags = split_sound_tags(content)
    if cleaned == content:
        return event
    metadata = event.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    if tags:
        metadata["sound_tags"] = [{"tag": tag.tag, "at": tag.at} for tag in tags]
    return {**event, "content": cleaned, "metadata": metadata}


__all__ = [
    "SOUND_TAG_CUES",
    "SoundTag",
    "sound_tag_name",
    "split_sound_tags",
    "strip_sound_tags",
    "strip_sound_tags_from_stream",
]
