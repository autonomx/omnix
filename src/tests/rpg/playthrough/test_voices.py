"""Playthrough: a campaign's voices (evolution roadmap EV-13). Reading the cast casts the narrator and each person
heard, among the castable voices only and outside the campaign document; the player's choice of a castable voice
stands, one not castable is refused; a response is planned for speech from its shown text, in its speakers' voices;
a sentence is streamed as it is synthesized, kept once whole, and played from the cache after."""
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


def _stream(spoken: list, pieces: tuple[bytes, ...] = (b"\x00\x01" * 120, b"\x02\x03" * 120), fail_after: int = 0,
            busy_first: bool = False):
    def stream(text: str, *, speaker: str, generation: dict):  # the speech service, as live speech streams it
        spoken.append((text, speaker, generation))
        if busy_first and len(spoken) == 1:
            from app.providers.qwen_http_gateway import TtsServiceSaturated

            raise TtsServiceSaturated("0")
        for index, piece in enumerate(pieces):
            if fail_after and index == fail_after:
                raise RuntimeError("the stream broke")
            yield piece, 24000

    return stream


def test_a_sentence_is_streamed_once_then_plays_from_the_campaigns_cache(launch, monkeypatch) -> None:
    from app.providers import tts_service

    spoken: list = []
    monkeypatch.setattr(tts_service, "stream_audio_pcm16", _stream(spoken))
    play = launch("aurelia")
    url = f"/api/rpg/sessions/{play.session_id}/speech-audio"
    first = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert first.status_code == 200 and first.headers["X-Omnix-Speech-Cache"] == "miss"
    assert first.headers["content-type"].startswith("application/x-omnix-pcm16")
    assert first.headers["X-Omnix-Sample-Rate"] == "24000" and first.content == b"\x00\x01" * 120 + b"\x02\x03" * 120
    narrator = {row["speaker_id"]: row for row in play.client.get(
        f"/api/rpg/sessions/{play.session_id}/voices").json()["cast"]}["narrator"]["voice_id"]
    # In the narrator's cast voice, on the CUDA-graph decode (the parity decode is slower than real time), with live
    # chat's token budget for the sentence (46 codec steps for these 19 characters) and least repetition penalty.
    assert spoken == [("The grove is quiet.", narrator,
                       {"chunk_size": 8, "parity_mode": False, "repetition_penalty": 1.05, "max_new_tokens": 46})]
    again = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert again.headers["X-Omnix-Speech-Cache"] == "hit" and again.content == first.content
    assert again.headers["X-Omnix-Sample-Rate"] == "24000" and len(spoken) == 1


def test_a_broken_stream_is_not_kept_and_a_service_down_is_silent(launch, monkeypatch) -> None:
    from app.providers import tts_service

    spoken: list = []
    monkeypatch.setattr(tts_service, "stream_audio_pcm16", _stream(spoken, fail_after=1))
    play = launch("aurelia")
    url = f"/api/rpg/sessions/{play.session_id}/speech-audio"
    broken = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert broken.status_code == 200 and broken.content == b"\x00\x01" * 120  # what was heard stands
    again = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert again.headers["X-Omnix-Speech-Cache"] == "miss" and len(spoken) == 2  # nothing was kept

    def down(text: str, *, speaker: str, generation: dict):
        raise RuntimeError("Real TTS generation failed")
        yield b"", 24000

    monkeypatch.setattr(tts_service, "stream_audio_pcm16", down)
    answer = play.client.post(url, json={"speaker_id": "narrator", "text": "The road is long."})
    assert answer.status_code == 503 and answer.json()["detail"]["error"] == "speech_unavailable"


def test_audio_that_ran_out_its_budget_is_not_kept_and_a_busy_device_is_tried_again(launch, monkeypatch) -> None:
    from app.providers import tts_service

    spoken: list = []
    # 3.6 s for "The grove is quiet.": 95% of its 46-step budget (3.68 s) or more, the model failing to stop.
    monkeypatch.setattr(tts_service, "stream_audio_pcm16", _stream(spoken, pieces=(b"\x00\x01" * 86_400,),
                                                                   busy_first=True))
    play = launch("aurelia")
    url = f"/api/rpg/sessions/{play.session_id}/speech-audio"
    first = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert first.status_code == 200 and len(spoken) == 2  # busy once, then spoken
    again = play.client.post(url, json={"speaker_id": "narrator", "text": "The grove is quiet."})
    assert again.headers["X-Omnix-Speech-Cache"] == "miss"  # the runaway was not kept
