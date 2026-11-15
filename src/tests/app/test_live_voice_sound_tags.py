"""Sound tags in live replies: the words are saved, the tags are recorded, and the prompt offers only recorded clips."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.conversation.sound_tags import SoundTag, split_sound_tags, strip_sound_tags, strip_sound_tags_from_stream


# --- Reading a reply ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "words", "tags"),
    [
        ("[hmm] Let me think.", "Let me think.", (SoundTag("hmm", 0),)),
        ("[Chuckles] That's good.", "That's good.", (SoundTag("chuckle", 0),)),
        ("[ sigh ] Fine.", "Fine.", (SoundTag("sigh", 0),)),
        ("[hmmm] Maybe.", "Maybe.", (SoundTag("hmm", 0),)),
        ("[laughs] Okay.", "Okay.", (SoundTag("chuckle", 0),)),
        ("Fine. [sigh] Let's go.", "Fine. Let's go.", (SoundTag("sigh", 6),)),
        ("Right [hmm], so.", "Right, so.", (SoundTag("hmm", 5),)),
    ],
)
def test_a_known_tag_leaves_the_words_and_its_place(text: str, words: str, tags: tuple[SoundTag, ...]) -> None:
    assert split_sound_tags(text) == (words, tags)


def test_other_bracketed_text_and_stray_brackets_are_never_read_aloud() -> None:
    assert split_sound_tags("Well [soft pause] okay ] then [") == ("Well okay then", ())
    assert strip_sound_tags("[grins] Sure [sigh]") == "Sure"


def test_a_reply_without_brackets_is_untouched() -> None:
    text = "First line.\nSecond line."
    assert split_sound_tags(text) == (text, ())


def test_the_finished_reply_is_saved_without_tags_and_remembers_them() -> None:
    closed: list[bool] = []

    def events():
        try:
            yield {"type": "text_chunk", "text": "[hmm] Let"}
            yield {"type": "complete", "content": "[hmm] Let me see.", "metadata": {"generation_status": "completed"}}
        finally:
            closed.append(True)

    out = list(strip_sound_tags_from_stream(events()))
    assert out[0] == {"type": "text_chunk", "text": "[hmm] Let"}
    assert out[1]["content"] == "Let me see."
    assert out[1]["metadata"] == {"generation_status": "completed", "sound_tags": [{"tag": "hmm", "at": 0}]}
    assert closed == [True]


def test_closing_the_stream_early_closes_the_reply_underneath() -> None:
    closed: list[bool] = []

    def events():
        try:
            yield {"type": "text_chunk", "text": "a"}
            yield {"type": "text_chunk", "text": "b"}
        finally:
            closed.append(True)

    stream = strip_sound_tags_from_stream(events())
    next(stream)
    stream.close()
    assert closed == [True]


# --- What the voice can play ----------------------------------------------------------------


def test_the_voice_has_the_cues_it_has_clips_for(tmp_path, monkeypatch) -> None:
    from app.platform.live_voice.transport.cue_asset_routes import voice_cue_ids

    monkeypatch.setenv("OMNIX_LIVE_VOICE_CUE_ROOT", str(tmp_path / "cues"))
    assert voice_cue_ids("Maya") == frozenset()
    assert not (tmp_path / "cues").exists()  # asking creates nothing

    voice = tmp_path / "cues" / "Maya"
    voice.mkdir(parents=True)
    for name in ("hmm-v1.wav", "hmm-v2.wav", "sigh-v1.wav", "laugh-v1.wav", "notes.txt"):
        (voice / name).write_bytes(b"RIFF")
    assert voice_cue_ids("Maya") == frozenset({"hmm", "sigh"})
    assert voice_cue_ids("../Maya") == frozenset()
    assert voice_cue_ids(None) == frozenset()


def test_tags_are_offered_for_recorded_clips_unless_attunement_is_off() -> None:
    from app.platform.live_voice.prompt.sound_tags import offered_sound_tags, sound_tags_prompt

    subtle = SimpleNamespace(emotional_attunement="subtle")
    off = SimpleNamespace(emotional_attunement="off")
    cues = frozenset({"hmm", "amused_exhale"})
    assert offered_sound_tags(subtle, cues) == ("hmm", "chuckle")
    assert offered_sound_tags(off, cues) == ()
    assert offered_sound_tags(subtle, frozenset({"mhm"})) == ()
    prompt = sound_tags_prompt(("hmm",))
    assert "[hmm]" in prompt and "[sigh]" not in prompt and "[chuckle]" not in prompt
    assert sound_tags_prompt(()) == ""


def test_the_prompt_offers_tags_before_the_conversation(tmp_path, monkeypatch) -> None:
    from app.platform.chat.contracts import RenderedPromptMessage
    from app.platform.live_voice import pipeline
    from app.platform.live_voice.prompt import cache

    voice = tmp_path / "Jinx"
    voice.mkdir()
    (voice / "hmm-v1.wav").write_bytes(b"RIFF")
    monkeypatch.setenv("OMNIX_LIVE_VOICE_CUE_ROOT", str(tmp_path))

    def context(speaker: str | None, attunement: str = "subtle"):
        monkeypatch.setattr(cache, "resolve_live_voice_speaker_cached", lambda _session: speaker)
        rendered = SimpleNamespace(
            messages=[RenderedPromptMessage(role="system", content="You are Jinx."),
                      RenderedPromptMessage(role="user", content="Hi")],
            diagnostics=SimpleNamespace(estimated_tokens=10, section_tokens={}),
        )
        ctx = SimpleNamespace(
            rendered=rendered,
            assembly=SimpleNamespace(diagnostics={}),
            session=SimpleNamespace(),
            profile=SimpleNamespace(emotional_attunement=attunement),
        )
        pipeline._add_sound_tags(ctx)
        return ctx

    offered = context("Jinx")
    assert [message.role for message in offered.rendered.messages] == ["system", "system", "user"]
    assert "[hmm]" in offered.rendered.messages[1].content and not offered.rendered.messages[1].per_turn
    assert offered.assembly.diagnostics["live_voice_sound_tags"]["tags"] == ["hmm"]
    assert offered.rendered.diagnostics.section_tokens["live_voice_sound_tags"] > 0
    assert len(context("Maya").rendered.messages) == 2  # no clips for this voice
    assert len(context(None).rendered.messages) == 2  # the server knows no voice
    assert len(context("Jinx", "off").rendered.messages) == 2


# --- The next turn continues the model's response -------------------------------------------


def test_a_tagged_reply_still_continues_on_the_next_turn() -> None:
    from app.platform.live_voice.llm import lmstudio_responses as runtime
    from app.providers import ChatMessage as ProviderMessage

    runtime._clear_response_states_for_tests()
    try:
        assert runtime._remember_response_state(
            session_id="chat:tags",
            model_id="model-a",
            request_messages=[ProviderMessage(role="system", content="persona"),
                              ProviderMessage(role="user", content="Funny?")],
            assistant_text="[chuckle] It was.",
            response_id="resp_tagged",
        ) is True
        response_id, reason, _count, _rolled = runtime._resolve_previous_response_id(
            session_id="chat:tags",
            model_id="model-a",
            messages=[ProviderMessage(role="system", content="persona"),
                      ProviderMessage(role="user", content="Funny?"),
                      ProviderMessage(role="assistant", content="It was."),
                      ProviderMessage(role="user", content="Why?")],
        )
        assert (response_id, reason) == ("resp_tagged", "hit")
    finally:
        runtime._clear_response_states_for_tests()
