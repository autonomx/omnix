"""A campaign's voices (evolution roadmap EV-13): casting picks only castable voices, the same for the same campaign,
keeps the author's castable choice, and gives two people one voice only when the list runs out; text is spoken by
sentence."""
from __future__ import annotations

import json

from app.apps.rpg.session.voice_cast import NARRATOR, auto_cast, speakers
from app.platform.voice.voice_casting import castable_voices, split_sentences

VOICES = [{"voice_id": "deep", "name": "Deep", "description": "an old man, gruff and slow", "revision": "r1"},
          {"voice_id": "bright", "name": "Bright", "description": "a young woman, quick and cheerful", "revision": "r2"},
          {"voice_id": "default", "name": "Narrator", "description": "a clear storyteller", "revision": "service"}]
PEOPLE = [{"speaker_id": NARRATOR, "name": "The narrator", "lore": "storyteller narrator", "voice": ""},
          {"speaker_id": "npc:orik", "name": "Orik", "lore": "an old innkeeper, gruff", "voice": ""},
          {"speaker_id": "npc:liora", "name": "Liora", "lore": "a young guide, quick", "voice": ""}]


def test_casting_is_the_campaigns_fits_the_lore_and_shares_no_voice_while_there_are_enough() -> None:
    cast = auto_cast("rpg_1", PEOPLE, VOICES, {})
    assert {speaker: row["voice_id"] for speaker, row in cast.items()} == {
        NARRATOR: "default", "npc:orik": "deep", "npc:liora": "bright"}
    assert auto_cast("rpg_1", PEOPLE, VOICES, {}) == cast  # the same campaign casts the same
    assert auto_cast("rpg_1", PEOPLE, VOICES[:1], {})["npc:liora"]["voice_id"] == "deep"  # one voice: shared


def test_only_castable_voices_are_cast_and_the_authors_castable_choice_is_kept() -> None:
    authored = [*PEOPLE[:2], {**PEOPLE[2], "voice": "deep"}]
    cast = auto_cast("rpg_1", authored, VOICES, {})
    assert cast["npc:liora"] == {"voice_id": "deep", "voice_revision": "r1", "chosen_by": "author"}
    not_castable = [{**PEOPLE[1], "voice": "someone-real"}]
    assert auto_cast("rpg_1", not_castable, VOICES, {})["npc:orik"]["chosen_by"] == "auto"
    assert auto_cast("rpg_1", PEOPLE, [], {}) == {}
    already = {"npc:orik": {"voice_id": "bright", "voice_revision": "r2", "chosen_by": "player"}}
    assert "npc:orik" not in auto_cast("rpg_1", PEOPLE, VOICES, already)  # the player's choice stands


def test_the_castable_list_offers_only_what_it_marks_castable(tmp_path) -> None:
    (tmp_path / "casting.json").write_text(json.dumps({"voices": {
        "kept": {"castable": True, "description": "calm"}, "held": {"castable": False, "description": "a clone"}}}))
    for name in ("kept", "held"):
        (tmp_path / f"{name}.json").write_text(json.dumps({"ref_text": name}))
        (tmp_path / f"{name}.wav").write_bytes(b"RIFF" + name.encode())
    assert [row["voice_id"] for row in castable_voices(tmp_path)] == ["kept"]


def test_who_is_cast_and_how_text_is_spoken() -> None:
    document = {"simulation_state": {"world_model": {"npcs": {"npc:orik": {"name": "Orik", "role": "innkeeper"}}},
                                     "dialogue": {"exchanges": {"npc:orik": [{"player": "hi", "npc": "hello"}]}}}}
    assert [row["speaker_id"] for row in speakers(document)] == [NARRATOR, "npc:orik"]
    assert split_sentences('Rain falls. "Stay," she says! Then? Quiet') == [
        "Rain falls.", '"Stay," she says!', "Then?", "Quiet"]
