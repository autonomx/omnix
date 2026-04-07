from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.providers.base import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


class AppLLMGateway:
    """Thin adapter from app.shared provider API to RPG LLM gateway shape.

    RPG narrator code expects:
        llm_gateway.call("generate", prompt, context={...}) -> str

    The app provider layer exposes:
        provider.chat_completion(messages=[...], stream=False) -> ChatResponse | str
    """

    def __init__(
        self,
        provider: Any,
        *,
        global_system_prompt: str = "",
        default_temperature: Optional[float] = None,
    ):
        self.provider = provider
        self.global_system_prompt = global_system_prompt or ""
        self.default_temperature = default_temperature

    def _build_messages(
        self,
        prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ChatMessage]:
        system_parts: List[str] = []
        if self.global_system_prompt:
            system_parts.append(self.global_system_prompt.strip())
        system_parts.append(
            "You are narrating and shaping content for a deterministic RPG system. "
            "Return only the requested content. "
            "Do not add markdown fences unless explicitly requested."
        )
        system_text = "\n\n".join(part for part in system_parts if part).strip()

        user_parts: List[str] = [prompt.strip()]
        if context:
            try:
                context_text = json.dumps(context, ensure_ascii=False, sort_keys=True)
            except Exception:
                context_text = "{}"
            user_parts.append("Context JSON:")
            user_parts.append(context_text)
        user_text = "\n\n".join(part for part in user_parts if part).strip()

        messages: List[ChatMessage] = []
        if system_text:
            messages.append(ChatMessage(role="system", content=system_text))
        messages.append(ChatMessage(role="user", content=user_text))
        return messages

    def generate(
        self,
        prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = self._build_messages(prompt, context=context)
        response = self.provider.chat_completion(messages=messages, stream=False)

        if isinstance(response, ChatResponse):
            return (response.content or "").strip()
        if response is None:
            return ""
        return str(response).strip()

    def call(
        self,
        method: str,
        prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if method != "generate":
            raise ValueError(f"Unsupported AppLLMGateway method: {method}")
        return self.generate(prompt, context=context)


def build_app_llm_gateway() -> Optional[AppLLMGateway]:
    """Build a narrator-compatible gateway from the app's centralized provider layer.

    Returns None when provider setup is unavailable or fails, allowing callers
    to fall back to deterministic template behavior.
    """
    try:
        import app.shared as shared

        provider = shared.get_provider()
        if not provider:
            return None

        global_system_prompt = ""
        try:
            global_system_prompt = shared.get_global_system_prompt() or ""
        except Exception:
            logger.debug("No global system prompt available for RPG LLM gateway", exc_info=True)

        return AppLLMGateway(
            provider,
            global_system_prompt=global_system_prompt,
        )
    except Exception:
        logger.exception("Failed to build app LLM gateway for RPG runtime")
        return None