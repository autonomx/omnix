"""Chat session platform contract."""
from .character_store import ChatSessionStore, InMemoryChatSessionStore, default_chat_store
from .live_agent_store import install_live_agent_store_hooks
from .models import (
    ChatMessage,
    ChatSession,
    ChatSessionListResponse,
    ChatSessionSummary,
    ChatTextAttachment,
    CreateChatSessionRequest,
    DeleteChatSessionResponse,
    SendChatMessageRequest,
    SendChatMessageResponse,
    UpdateChatResearchModeRequest,
)
from .prompt_assembly import PromptAssembly, build_prompt_assembly
from .prompt_rendering import RenderedPrompt, render_prompt_assembly
from .prompt_store import chat_sqlite_store_enabled
from .repository import ChatImportState, ChatRepository, InMemoryChatRepository

install_live_agent_store_hooks(ChatSessionStore, InMemoryChatSessionStore)

__all__ = [
    "ChatImportState",
    "ChatMessage",
    "ChatRepository",
    "ChatSession",
    "ChatSessionListResponse",
    "ChatSessionStore",
    "ChatSessionSummary",
    "ChatTextAttachment",
    "CreateChatSessionRequest",
    "DeleteChatSessionResponse",
    "InMemoryChatRepository",
    "InMemoryChatSessionStore",
    "PromptAssembly",
    "RenderedPrompt",
    "SendChatMessageRequest",
    "SendChatMessageResponse",
    "UpdateChatResearchModeRequest",
    "build_prompt_assembly",
    "chat_sqlite_store_enabled",
    "default_chat_store",
    "render_prompt_assembly",
]
