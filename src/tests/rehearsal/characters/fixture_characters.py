"""The characters a rehearsal makes for itself, which leave the character list once the run has finished."""
from __future__ import annotations

import re
from typing import Any, Iterable, Protocol

_FIXTURE_ID = re.compile(r"stage\d+-")


class FixtureCharacterGateway(Protocol):
    def list_characters(self) -> list[dict[str, Any]]: ...
    def archive_character(self, character_id: str) -> dict[str, Any]: ...


def _archived_ids(gateway: FixtureCharacterGateway) -> set[str]:
    return {str(item.get("id")) for item in gateway.list_characters() if item.get("status") == "archived"}


def _free_id(character_id: str, archived: set[str]) -> str:
    if not _FIXTURE_ID.match(character_id) or character_id not in archived:
        return character_id
    suffix = 2
    while f"{character_id}-{suffix}" in archived:
        suffix += 1
    return f"{character_id}-{suffix}"


def free_fixture_ids(
    gateway: FixtureCharacterGateway,
    ids: dict[str, str],
) -> tuple[dict[str, str], str, dict[str, Any]]:
    """The character ids a new run uses, by config field.

    Nothing restores an archived character, so its id stays taken and a fixture moves to the next one. A leftover from
    a run that did not finish is still active and is used again.
    """
    archived = _archived_ids(gateway)
    free = {field: _free_id(character_id, archived) for field, character_id in ids.items()}
    return free, "This run's fixture character ids are not archived.", {"character_ids": free}


def archive_fixture_characters(gateway: FixtureCharacterGateway, character_ids: Iterable[str]) -> list[str]:
    """Archives a finished run's fixtures; a real character named on the command line is not the run's to remove."""
    archived = _archived_ids(gateway)
    targets = [item for item in character_ids if _FIXTURE_ID.match(item) and item not in archived]
    for character_id in targets:
        gateway.archive_character(character_id)
    return targets


__all__ = ["FixtureCharacterGateway", "archive_fixture_characters", "free_fixture_ids"]
