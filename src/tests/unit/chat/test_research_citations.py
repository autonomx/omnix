from app.chat import ChatMessage, ChatSessionStore, CreateChatSessionRequest
from app.chat.research_citations import validate_completed_research_reply


def test_completed_quick_reply_persists_validation_and_manifest(tmp_path) -> None:
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Research"))
    user = ChatMessage(
        id="msg:user",
        role="user",
        content="What changed?",
        created_at="2026-07-06T00:00:00Z",
    )
    assistant = ChatMessage(
        id="msg:assistant",
        role="assistant",
        content="The release changed today [S1].",
        created_at="2026-07-06T00:00:01Z",
    )
    session.messages.extend((user, assistant))
    session.message_count = len(session.messages)
    store._save_sessions([session])  # noqa: SLF001 - persistence fixture

    context_items = [
        {
            "source_id": "web_search",
            "title": "[S1] Release",
            "content": "Citation label: [S1].",
            "url": "https://example.test/release",
            "metadata": {
                "citation_label": "S1",
                "source_record_id": "source:one",
                "snapshot_id": "snapshot:one",
                "source_manifest_id": "manifest:one",
            },
        }
    ]
    updated = validate_completed_research_reply(store, session.id, user.id, context_items)

    assert updated is not None
    saved = updated.messages[-1]
    assert saved.metadata["research_mode"] == "quick"
    assert saved.metadata["research_status"] == "completed"
    assert saved.metadata["source_manifest_id"] == "manifest:one"
    assert saved.metadata["citation_validation"]["valid"] is True
    assert "structured output was unavailable" in saved.content
