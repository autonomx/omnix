"""A campaign's voices (evolution roadmap EV-13): the narrator and every person who speaks, each heard in a voice.

The cast is presentation, kept outside the campaign document (``omnix_rpg_voice_cast``), so it changes no turn and
no replay. Who is cast: the narrator, and each person the hero has heard (anyone with an exchange in the dialogue's
record) or meets now. How (``auto_cast``): deterministically, seeded by the campaign and the person, among the
castable voices only (``platform/voice/voice_casting.py``), the voice whose description shares most words with the
person's lore (their role, their description), and where the castable list has enough, never one already given to
someone in the same scene. The world's author may name voices for its people (a person's ``voice``); a castable one
is kept. The player may choose any castable voice for anyone (``choose``), and their choice wins.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state import access as _sections

NARRATOR = "narrator"
_WORDS = re.compile(r"[a-z]{3,}")


def speakers(document: Mapping[str, Any]) -> list[dict[str, str]]:
    """Who has a voice in the campaign: the narrator, then each person heard or present, with their lore to cast by."""
    simulation = _d(_sections.simulation_state_of(document))
    people = _d(_d(_sections.world_model_of(simulation)).get("npcs"))
    heard = list(_d(_d(simulation.get("dialogue")).get("exchanges")))
    present = [_s(npc) for npc in _l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids"))]
    found = [{"speaker_id": NARRATOR, "name": "The narrator", "lore": "storyteller narrator", "voice": ""}]
    for npc_id in dict.fromkeys([*heard, *present]):
        row = _d(people.get(npc_id))
        if row:
            found.append({"speaker_id": str(npc_id), "name": _s(row.get("name")) or str(npc_id),
                          "lore": f"{_s(row.get('role'))} {_s(row.get('description'))}", "voice": _s(row.get("voice"))})
    return found


def auto_cast(campaign_id: str, people: Iterable[Mapping[str, str]], voices: list[dict[str, Any]],
              cast: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str]]:
    """The voices for the people not cast yet: the author's where castable, else the best fitting castable voice not
    already heard in the scene, ties broken by a roll seeded by the campaign and the person."""
    from app.apps.rpg.foundation.core.determinism import rng_for, rng_seed_from_session_id, stable_sub_index

    castable = {row["voice_id"]: row for row in voices}
    if not castable:
        return {}
    taken = {row["voice_id"] for row in cast.values()}
    made: dict[str, dict[str, str]] = {}
    seed = rng_seed_from_session_id(campaign_id)
    for person in people:
        speaker = person["speaker_id"]
        if speaker in cast:
            continue
        if person.get("voice") in castable:
            choice, chosen_by = person["voice"], "author"
        else:
            words = set(_WORDS.findall(person.get("lore", "").casefold()))
            free = [voice for voice in castable if voice not in taken] or list(castable)
            rng = rng_for(seed, 0, "voice_cast", stable_sub_index(speaker))
            choice = max(sorted(free), key=lambda voice: (
                len(words & set(_WORDS.findall(castable[voice]["description"].casefold()))), rng.random()))
            chosen_by = "auto"
        made[speaker] = {"voice_id": choice, "voice_revision": castable[choice]["revision"], "chosen_by": chosen_by}
        taken.add(choice)
    return made


def cast_for(work: Any, context: Any, campaign_id: str, document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The campaign's cast, the people first heard or met since cast now: each speaker with their voice."""
    from app.platform.voice.voice_casting import castable_voices

    voices = castable_voices()
    revisions = {row["voice_id"]: row["revision"] for row in voices}
    people = speakers(document)
    # A voice taken off the castable list, or whose recording changed, is no longer this campaign's: recast it.
    cast = {speaker: row for speaker, row in work.rpg_voice_cast.cast(context, campaign_id).items()
            if revisions.get(row.get("voice_id", "")) == row.get("voice_revision")}
    for speaker, row in auto_cast(campaign_id, people, voices, cast).items():
        work.rpg_voice_cast.put(context, campaign_id, speaker, **{**row, "replace": True})
        cast[speaker] = row
    return [{"speaker_id": person["speaker_id"], "name": person["name"], **cast.get(person["speaker_id"], {})}
            for person in people]


def choose(work: Any, context: Any, campaign_id: str, speaker_id: str, voice_id: str,
           document: Mapping[str, Any]) -> dict[str, str] | None:
    """The player's choice of a castable voice for someone who speaks in the campaign (None: the voice may not be
    offered to them, or no such speaker)."""
    from app.platform.voice.voice_casting import castable_voices

    voice = next((row for row in castable_voices() if row["voice_id"] == voice_id), None)
    if voice is None or speaker_id not in {row["speaker_id"] for row in speakers(document)}:
        return None
    work.rpg_voice_cast.put(context, campaign_id, speaker_id, voice_id=voice_id, voice_revision=voice["revision"],
                            chosen_by="player")
    return {"voice_id": voice_id, "voice_revision": voice["revision"], "chosen_by": "player"}


__all__ = ["NARRATOR", "auto_cast", "cast_for", "choose", "speakers"]
