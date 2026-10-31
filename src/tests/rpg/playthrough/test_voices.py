"""Playthrough: a campaign's voices (evolution roadmap EV-13). Reading the cast casts the narrator and each person
heard, among the castable voices only and outside the campaign document; the player's choice of a castable voice
stands, one not castable is refused; a response is planned for speech from its shown text, in its speakers' voices."""
from __future__ import annotations

from tests.rpg.playthrough.campaigns import POSTGRES
from tests.rpg.playthrough.scripted_model import Role

pytestmark = POSTGRES


def test_the_cast_is_castable_voices_only_and_the_players_choice_stands(launch) -> None:
    from app.platform.voice.voice_casting import castable_voices

    play = launch("aurelia")
    play.model.answer(Role.DIALOGUE, ("Liora Fen", "Stay close. The grove is restless."))
    play.turn("ask Liora Fen what is going on")
    revision = play.revision()
    url = f"/api/rpg/sessions/{play.session_id}/voices"
    body = play.client.get(url).json()
    castable = {row["voice_id"] for row in castable_voices()}
    cast = {row["speaker_id"]: row for row in body["cast"]}
    assert {"narrator", "npc:liora-fen"} <= set(cast)
    assert all(row["voice_id"] in castable for row in cast.values())
    assert play.revision() == revision  # the cast is not the game's state
    refused = play.client.put(f"{url}/npc:liora-fen", json={"voice_id": "not-on-the-list"})
    assert refused.status_code == 422
    choice = sorted(castable)[0]
    chosen = play.client.put(f"{url}/npc:liora-fen", json={"voice_id": choice}).json()
    assert {row["speaker_id"]: row for row in chosen["cast"]}["npc:liora-fen"]["chosen_by"] == "player"
    planned = play.client.post(f"/api/rpg/sessions/{play.session_id}/speech-plan", json={"blocks": [
        {"speaker_id": "npc:liora-fen", "text": "Stay close. The grove is restless."}]}).json()
    assert planned["segments"] == [{"speaker_id": "npc:liora-fen", "voice_id": choice,
                                    "sentences": ["Stay close.", "The grove is restless."]}]


def test_a_sentence_is_synthesized_once_then_plays_from_the_campaigns_cache(launch) -> None:
    play = launch("aurelia")
    url = f"/api/rpg/sessions/{play.session_id}/speech-audio"
    first = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert first.status_code == 200 and first.headers["X-Omnix-Speech-Cache"] == "miss"
    assert first.content[:4] == b"RIFF"
    again = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert again.headers["X-Omnix-Speech-Cache"] == "hit" and again.content == first.content
