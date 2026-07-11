from app.assistant_context.models import AssistantContextChatRequest
from app.assistant_context.service import AssistantContextService


def test_live_conversation_repair_is_bounded_trusted_context() -> None:
    request = AssistantContextChatRequest(
        content="Actually, I meant Tuesday.",
        live_repair={
            "kind": "acknowledge_correction",
            "instruction": "Acknowledge the correction briefly and continue.",
            "source_reason": "correction",
            "confidence": 0.9,
        },
    )

    result = AssistantContextService().build(request)

    repair = next(item for item in result.items if item.source_id == "live_repair")
    assert repair.title == "Live conversation repair guidance"
    assert "Trusted conversational-control guidance" in repair.content
    assert repair.metadata["kind"] == "acknowledge_correction"
    assert repair.metadata["trusted_control_context"] is True
    assert result.diagnostics["live_repair_requested"] is True
    assert result.diagnostics["live_repair_kind"] == "acknowledge_correction"


def test_live_conversation_repair_is_optional() -> None:
    result = AssistantContextService().build(AssistantContextChatRequest(content="Hello"))

    assert all(item.source_id != "live_repair" for item in result.items)
    assert result.diagnostics["live_repair_requested"] is False
