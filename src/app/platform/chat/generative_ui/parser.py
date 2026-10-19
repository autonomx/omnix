"""Find ```omnix-ui fences in a reply and parse their JSON tolerantly.

The fence grammar is the client renderer's (``markdownRenderer.ts``): a fence
opens on a line of at most three spaces, three backticks and an info string,
and closes on a line of at most three spaces and three backticks. Any fence
can contain ```omnix-ui lines without opening a block. Offsets index the
original text, line endings included, so Markdown spans can be sliced from the
stored content exactly.

JSON parsing here is deliberately tolerant and separate from the strict
structured-output parser (``providers/structured/parsing.py``): it repairs
trailing commas, smart quotes and single-quoted strings, and says so.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

UI_INFO_STRING = "omnix-ui"
# The client's regexes, with ``\w`` ASCII-only as in JavaScript.
_FENCE_OPEN = re.compile(r"^\s{0,3}```\s*([\w+-]*)\s*$", re.ASCII)
_FENCE_CLOSE = re.compile(r"^\s{0,3}```\s*$", re.ASCII)


@dataclass(frozen=True)
class Fence:
    """One ```omnix-ui fence: ``start``/``end`` cover its lines, ``body`` is the text between them."""

    start: int
    end: int
    body: str
    closed: bool


@dataclass(frozen=True)
class ParsedJson:
    value: Any
    repaired: bool


class FenceJsonError(ValueError):
    """The fence body is not JSON even after repair."""


def _lines(content: str) -> Iterator[tuple[int, int, str]]:
    """(start, end_including_terminator, text_without_terminator) for each line."""
    position = 0
    length = len(content)
    while position < length:
        newline = content.find("\n", position)
        carriage = content.find("\r", position)
        if carriage != -1 and (newline == -1 or carriage < newline):
            stop = carriage
            after = carriage + 2 if content.startswith("\r\n", carriage) else carriage + 1
        elif newline != -1:
            stop, after = newline, newline + 1
        else:
            stop, after = length, length
        yield position, after, content[position:stop]
        position = after


def scan_fences(content: str) -> list[Fence]:
    """The ```omnix-ui fences in ``content``, in order. Other fences are skipped whole."""
    fences: list[Fence] = []
    open_start: int | None = None
    open_ui = False
    body_start = 0
    for start, end, line in _lines(content):
        if open_start is None:
            match = _FENCE_OPEN.match(line)
            if match:
                open_start, open_ui, body_start = start, match.group(1) == UI_INFO_STRING, end
            continue
        if _FENCE_CLOSE.match(line):
            if open_ui:
                fences.append(Fence(open_start, end, content[body_start:start], closed=True))
            open_start = None
    if open_start is not None and open_ui:
        fences.append(Fence(open_start, len(content), content[body_start:], closed=False))
    return fences


def parse_fence_json(body: str) -> ParsedJson:
    """Parse a fence body as JSON, repairing common model mistakes when strict parsing fails."""
    text = body.strip()
    try:
        return ParsedJson(json.loads(text), repaired=False)
    except json.JSONDecodeError:
        pass
    repaired = _repair(text)
    try:
        return ParsedJson(json.loads(repaired), repaired=True)
    except json.JSONDecodeError as error:
        raise FenceJsonError(str(error)) from error


_CLOSERS = {'"': '"', "“": "”", "'": "'", "‘": "’"}
_ALTERNATE_CLOSERS = {"“": '"', "‘": "'"}


def _repair(text: str) -> str:
    """Rewrite smart-quoted and single-quoted strings as JSON strings and drop trailing commas. Linear time."""
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in _CLOSERS:
            closer = _CLOSERS[char]
            alternate = _ALTERNATE_CLOSERS.get(char)
            raw: list[str] = []
            index += 1
            while index < length:
                current = text[index]
                if current == "\\" and index + 1 < length:
                    raw.append(text[index : index + 2])
                    index += 2
                    continue
                if current == closer or current == alternate:
                    index += 1
                    break
                raw.append(current)
                index += 1
            out.append(_json_string("".join(raw), plain=char == '"'))
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < length and text[lookahead] in " \t\r\n":
                lookahead += 1
            if lookahead < length and text[lookahead] in "}]":
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _json_string(raw: str, *, plain: bool) -> str:
    if plain:
        return f'"{raw}"'
    # Non-JSON delimiters: unescape \' and escape bare double quotes.
    pieces: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 1 < len(raw):
            pair = raw[index : index + 2]
            pieces.append("'" if pair == "\\'" else pair)
            index += 2
            continue
        pieces.append('\\"' if char == '"' else char)
        index += 1
    return '"' + "".join(pieces) + '"'
