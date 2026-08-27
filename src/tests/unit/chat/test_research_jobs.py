from __future__ import annotations

from app.chat.models import ChatMessage, ChatSession
from app.chat.research_jobs import link_user_message_to_research_job


class TargetedMetadataStore:
    def __init__(self, session: ChatSession) -> None:
        self.sessions = [session]
        self.updates: list[dict[str, object]] = []

    def update_user_message_metadata(
        self,
        *,
        session_id: str,
        message_id: str,
        metadata: dict[str, object],
    ) -> bool:
        self.updates.append(
            {
                "session_id": session_id,
                "message_id": message_id,
                "metadata": dict(metadata),
            }
        )
        for session in self.sessions:
            for message in session.messages:
                if session.id == session_id and message.id == message_id:
                    message.metadata.update(metadata)
                    return True
        return False

    def _load_sessions(self) -> list[ChatSession]:
        return self.sessions


def test_research_job_id_is_persisted_with_targeted_postgres_style_update() -> None:
    message = ChatMessage(
        id="msg:user",
        role="user",
        content="Research Nvidia",
        created_at="2026-08-27T03:13:23Z",
    )
    session = ChatSession(
        id="chat:test",
        title="Research chat",
        messages=[message],
        message_count=1,
        created_at="2026-08-27T03:13:23Z",
        updated_at="2026-08-27T03:13:23Z",
    )
    store = TargetedMetadataStore(session)

    linked = link_user_message_to_research_job(
        store,  # type: ignore[arg-type]
        session.id,
        message.id,
        "job:new-outline",
    )

    assert linked is not None
    assert linked[1].metadata["research_job_id"] == "job:new-outline"
    assert store.updates == [
        {
            "session_id": "chat:test",
            "message_id": "msg:user",
            "metadata": {
                "research_mode": "deep",
                "research_status": "queued",
                "research_job_id": "job:new-outline",
            },
        }
    ]
