import pytest
from pydantic import ValidationError

from app.chat.models import ChatMessage, ChatSession, CreateChatSessionRequest, SendChatMessageRequest
from app.chat.prompt_assembly import PromptAssembly, PromptTurn
from app.chat.prompt_rendering import render_prompt_assembly
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore
from app.chat.store import ChatSessionStore
from app.providers import ChatMessage as ProviderMessage
from app.providers.chatgpt_codex_provider import ChatGPTCodexProvider


IMAGE_DATA_URL = "data:image/png;base64,aW1hZ2UtZGF0YQ=="
SECOND_IMAGE_DATA_URL = "data:image/jpeg;base64,c2Vjb25kLWltYWdl"


def _session() -> ChatSession:
    return ChatSession(
        id="chat:image",
        title="Image chat",
        created_at="2026-08-29T00:00:00Z",
        updated_at="2026-08-29T00:00:00Z",
    )


def test_send_chat_request_validates_supported_image_data_url():
    legacy = SendChatMessageRequest(content="Describe this", image_data_url=IMAGE_DATA_URL)
    assert legacy.image_data_url == IMAGE_DATA_URL
    assert legacy.image_data_urls == [IMAGE_DATA_URL]

    request = SendChatMessageRequest(
        content="Compare these",
        image_data_urls=[IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL],
    )
    assert request.image_data_url == IMAGE_DATA_URL
    assert request.image_data_urls == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]

    with pytest.raises(ValidationError, match="PNG, JPEG, or WebP"):
        SendChatMessageRequest(content="Describe this", image_data_urls=["data:image/gif;base64,R0lGODlh"])

    with pytest.raises(ValidationError, match="valid base64"):
        SendChatMessageRequest(content="Describe this", image_data_urls=["data:image/png;base64,not base64"])

    with pytest.raises(ValidationError):
        SendChatMessageRequest(content="Too many", image_data_urls=[IMAGE_DATA_URL] * 9)


def test_provider_messages_preserve_pasted_image_for_base_and_prompt_stores(tmp_path):
    user_message = ChatMessage(
        id="msg:image",
        role="user",
        content="Describe this",
        created_at="2026-08-29T00:00:01Z",
        metadata={
            "image_data_url": IMAGE_DATA_URL,
            "image_data_urls": [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL],
            "text_attachment": {
                "filename": "notes.md",
                "mime_type": "text/markdown",
                "text": "# Important notes",
            },
        },
    )
    session = _session()
    base_messages = ChatSessionStore(tmp_path / "chat.json")._provider_messages(session, user_message, [])

    base_image_urls = [item["image_url"]["url"] for item in base_messages[-1].to_dict()["content"] if item.get("type") == "image_url"]
    assert base_image_urls == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]
    assert "[Attached file: notes.md (text/markdown)]" in base_messages[-1].content

    assembly = PromptAssembly(current_user_message=PromptTurn(role="user", content=user_message.content, message_id=user_message.id))
    rendered = render_prompt_assembly(assembly)
    prompt_messages = PromptChatSessionStore._provider_messages_from_rendered(session, user_message, rendered)

    prompt_image_urls = [item["image_url"]["url"] for item in prompt_messages[-1].to_dict()["content"] if item.get("type") == "image_url"]
    assert prompt_image_urls == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]
    assert "# Important notes" in prompt_messages[-1].content


def test_chat_store_persists_multiple_image_attachments(tmp_path):
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Images"))
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="Compare these",
            image_data_urls=[IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL],
        ),
    )

    assert appended is not None
    _session, message = appended
    assert message.metadata["image_data_urls"] == [IMAGE_DATA_URL, SECOND_IMAGE_DATA_URL]
    assert message.metadata["image_data_url"] == IMAGE_DATA_URL


def test_chat_store_persists_text_file_attachment(tmp_path):
    store = ChatSessionStore(tmp_path / "chat.json")
    session = store.create_session(CreateChatSessionRequest(title="Attachment"))
    appended = store.begin_user_message(
        session.id,
        SendChatMessageRequest(
            content="Summarize this",
            text_attachment={
                "filename": "plan.txt",
                "mime_type": "text/plain",
                "text": "Ship the attachment feature.",
            },
        ),
    )

    assert appended is not None
    _session, message = appended
    assert message.metadata["text_attachment"]["filename"] == "plan.txt"


def test_codex_turn_input_uses_app_server_image_user_input():
    messages = [
        ProviderMessage(
            role="user",
            content="Describe this",
            vision_images=[{"data": IMAGE_DATA_URL}],
        )
    ]

    assert ChatGPTCodexProvider._turn_input(messages, "Describe this") == [
        {"type": "text", "text": "Describe this"},
        {"type": "image", "url": IMAGE_DATA_URL},
    ]


def test_codex_turn_input_preserves_images_when_rebuilding_history():
    first_image = "data:image/png;base64,Zmlyc3Q="
    latest_image = "data:image/png;base64,bGF0ZXN0"
    messages = [
        ProviderMessage(role="user", content="First image", vision_images=[{"data": first_image}]),
        ProviderMessage(role="assistant", content="First answer"),
        ProviderMessage(role="user", content="Second image", vision_images=[{"data": latest_image}]),
    ]

    inputs = ChatGPTCodexProvider._turn_input(messages, "Recovered history", recover_history=True)

    assert {item.get("url") for item in inputs if item["type"] == "image"} == {first_image, latest_image}
    assert any(item.get("text", "").startswith("The following image belongs to the reconstructed user message 1") for item in inputs)
