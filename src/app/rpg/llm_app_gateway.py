from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterator, List, Optional

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
        logger.debug("[RPG GATEWAY] Building messages, prompt length: %d, context keys: %s", len(prompt), list(context.keys()) if context else [])

        # For RPG narration, use a specific system prompt that overrides the global one
        system_text = (
            "You are a deterministic RPG narration engine. "
            "Your only task is to generate structured RPG narration responses. "
            "Return only the requested content in the exact format specified. "
            "Do not add extra text, explanations, or commentary."
        )

        user_parts: List[str] = [prompt.strip()]
        if context:
            try:
                context_text = json.dumps(context, ensure_ascii=False, sort_keys=True)
                logger.debug("[RPG GATEWAY] Context JSON length: %d", len(context_text))
            except Exception as e:
                logger.warning("[RPG GATEWAY] Failed to serialize context: %s", e)
                context_text = "{}"
            user_parts.append("Context JSON:")
            user_parts.append(context_text)
        user_text = "\n\n".join(part for part in user_parts if part).strip()

        messages: List[ChatMessage] = []
        if system_text:
            messages.append(ChatMessage(role="system", content=system_text))
        messages.append(ChatMessage(role="user", content=user_text))

        logger.debug("[RPG GATEWAY] Built %d messages", len(messages))
        return messages

    def generate(
        self,
        prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> str:
        # NOTE: timeout_s is accepted for forward-compatible API shape but is
        # intentionally not wired to the underlying provider yet.  Callers may
        # pass it to express intent; actual timeout enforcement will be added
        # when the provider abstraction gains native support.
        t0 = time.monotonic()
        logger.info(
            "[RPG GATEWAY] generate_start prompt_len=%d timeout_s=%s",
            len(prompt),
            timeout_s,
        )
        messages = self._build_messages(prompt, context=context)
        logger.debug("[RPG GATEWAY] Built messages for chat_completion", extra={"message_count": len(messages)})
        try:
            response = self.provider.chat_completion(messages=messages, stream=False)
            logger.info(
                "[RPG GATEWAY] generate_end dt=%.3fs response_type=%s",
                time.monotonic() - t0,
                type(response).__name__,
            )
            logger.debug("[RPG GATEWAY] Provider returned type: %s", type(response))
        except Exception:
            logger.exception("[RPG GATEWAY] Provider call failed")
            raise

        if isinstance(response, ChatResponse):
            content = (response.content or "").strip()
            logger.info("[RPG GATEWAY] ChatResponse content length: %d", len(content))
            return content
        if response is None:
            logger.warning("[RPG GATEWAY] Provider returned None")
            return ""
        content = str(response).strip()
        logger.debug("[RPG GATEWAY] Provider returned string length: %d", len(content))
        return content

    def generate_stream(
        self,
        prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        timeout_s: Optional[float] = None,
    ) -> Iterator[Dict[str, Any]]:
        # NOTE: timeout_s is accepted for forward-compatible API shape but is
        # intentionally not wired to the underlying provider yet.
        t0 = time.monotonic()
        chunk_count = 0
        first_chunk_at = None
        logger.info(
            "[RPG GATEWAY] stream_start prompt_len=%d timeout_s=%s",
            len(prompt),
            timeout_s,
        )
        messages = self._build_messages(prompt, context=context)
        logger.debug("[RPG GATEWAY] Built messages for streaming chat_completion", extra={"message_count": len(messages)})
        try:
            for chunk in self.provider.chat_completion(messages=messages, stream=True):
                if first_chunk_at is None:
                    first_chunk_at = time.monotonic()
                    logger.info(
                        "[RPG GATEWAY] stream_first_chunk dt=%.3fs",
                        first_chunk_at - t0,
                    )
                chunk_count += 1
                if isinstance(chunk, ChatResponse):
                    content = chunk.content or ""
                    if content:
                        yield {"text": content}
                else:
                    logger.warning("[RPG GATEWAY] Unexpected chunk type during streaming: %s", type(chunk))
            logger.info(
                "[RPG GATEWAY] stream_end total_dt=%.3fs chunk_count=%d",
                time.monotonic() - t0,
                chunk_count,
            )
        except Exception:
            logger.exception("[RPG GATEWAY] Streaming provider call failed")
            raise

    def complete(self, prompt: str) -> Dict[str, Any]:
        response = self.generate(prompt)
        if isinstance(response, dict):
            return {
                "text": str(response.get("text") or response.get("content") or ""),
                "raw": response,
            }
        return {"text": str(response or ""), "raw": response}

    def complete_json(self, prompt: str) -> Dict[str, Any]:
        response = self.complete(prompt)
        text = str(response.get("text") or "").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    def call(
        self,
        method: str,
        prompt: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if method == "generate":
            return self.generate(prompt, context=context)
        elif method == "generate_stream":
            return self.generate_stream(prompt, context=context)
        else:
            raise ValueError(f"Unsupported AppLLMGateway method: {method}")


def build_app_llm_gateway() -> Optional[AppLLMGateway]:
    """Build a narrator-compatible gateway from the app's centralized provider layer.

    Returns None when provider setup is unavailable or fails, allowing callers
    to fall back to deterministic template behavior.
    """
    try:
        import app.shared as shared

        provider = shared.get_provider()
        if not provider:
            logger.debug("RPG LLM gateway unavailable: app.shared.get_provider() returned no provider")
            return None

        logger.debug("RPG LLM gateway created successfully using centralized app provider")

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