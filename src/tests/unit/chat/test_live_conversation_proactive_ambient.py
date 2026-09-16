from types import SimpleNamespace

from app.chat import live_conversation_proactive


class FakeProvider:
    def chat_completion(self, *, messages, model, stream):
        assert stream is True
        return [SimpleNamespace(content="SKIP", model=model, usage=None)]


class FakeStore:
    def _provider_messages(self, session, synthetic_message, attachments):
        assert synthetic_message.metadata["transient"] is True
        assert attachments == []
        return []


def test_ambient_visual_presence_model_skip_is_not_emitted_as_spoken_text(monkeypatch) -> None:
    provider = FakeProvider()
    monkeypatch.setattr(live_conversation_proactive.shared, "get_provider", lambda _: provider)
    session = SimpleNamespace(
        provider_id="lmstudio",
        model_id="local-model",
        messages=[],
    )

    events = list(
        live_conversation_proactive.stream_proactive_turn_chunks(
            FakeStore(),
            session,
            initiative_reason="ambient_visual_presence",
            state_summary="desktop=user is still debugging the same failing test",
        )
    )

    assert [event["type"] for event in events] == ["initiative", "complete"]
    assert events[-1]["content"] == ""
    assert events[-1]["metadata"]["generation_status"] == "skipped"
    assert events[-1]["metadata"]["skip_reason"] == "ambient_model_skip"
