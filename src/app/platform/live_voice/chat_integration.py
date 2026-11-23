"""Live-voice adapters injected into Chat through the shared conversation port."""
from __future__ import annotations

from typing import Any, Iterator

from app.conversation.contracts import LiveVoiceChatPort

from .llm.routing import ROUTE_METADATA_KEY


class LiveVoiceChatIntegration:
    """Bind voice prompt and provider stages without patching Chat classes."""

    route_metadata_key = ROUTE_METADATA_KEY

    def build_live_voice_prompt(
        self,
        store: Any,
        session: Any,
        user_message: Any,
        context_items: list[dict[str, Any]] | None,
    ) -> tuple[Any, Any]:
        from .pipeline import build_live_voice_prompt

        return build_live_voice_prompt(store, session, user_message, context_items)

    def record_rendered_prompt(self, assembly: Any, rendered: Any) -> None:
        from .llm.lmstudio_diagnostics import record_rendered_prompt

        record_rendered_prompt(assembly, rendered)

    def begin_routed_user_message(
        self,
        store: Any,
        session_id: str,
        request: Any,
        *,
        persist: Any,
    ) -> Any:
        from .llm.routing import begin_routed_user_message

        return begin_routed_user_message(store, session_id, request, persist=persist)

    def route_reply(
        self,
        user_message: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
        request: Any = None,
    ) -> Any:
        """The provider and model that serve this reply, logged as the call's route.

        A non-streamed reply passes its ``request``, whose own provider or model choice may lead the route.
        """
        from .llm.routing import log_provider_route, resolve_generation_route, resolve_stream_route

        if request is None:
            route = resolve_stream_route(user_message, provider_id=provider_id, model_id=model_id)
            requested = provider_id
        else:
            route = resolve_generation_route(user_message, provider_id=provider_id, model_id=model_id, request=request)
            requested = request.provider_id or provider_id
        log_provider_route(requested_provider_id=requested, route=route, stream=request is None)
        return route

    def stream_with_retry(
        self,
        stream_factory: Any,
        fallback_factory: Any,
        *,
        provider_id: str | None,
        model_id: str | None,
    ) -> Iterator[Any]:
        from .llm.retry import stream_with_retry

        yield from stream_with_retry(
            stream_factory,
            fallback_factory,
            provider_id=provider_id,
            model_id=model_id,
        )

    def generate_reply(self, store: Any, session: Any, user_message: Any, *, provider: Any, **kwargs: Any) -> Any:
        """The whole reply from LM Studio, or None when another provider serves it and chat asks that one itself."""
        from .llm import lmstudio_diagnostics, metrics

        if not metrics.is_lmstudio_provider(provider):
            return None
        return lmstudio_diagnostics.generate_lmstudio_reply(
            store,
            session,
            user_message,
            fallback_generate=metrics.generate_lmstudio_reply,
            provider=provider,
            **kwargs,
        )

    def stream_reply(
        self, store: Any, session: Any, user_message: Any, *, provider: Any, **kwargs: Any
    ) -> Iterator[Any]:
        """Stream the reply: the LM Studio path for LM Studio, the low-latency stream for any other provider."""
        from .llm import lmstudio_responses, metrics
        from .llm.stream import stream_low_latency_reply

        if metrics.is_lmstudio_provider(provider):
            yield from lmstudio_responses.stream_lmstudio_reply(
                store,
                session,
                user_message,
                fallback_stream=metrics.stream_lmstudio_reply,
                provider=provider,
                **kwargs,
            )
            return
        yield from stream_low_latency_reply(store, session, user_message, provider=provider, **kwargs)

    def lmstudio_live_voice_options(self, user_message: Any) -> dict[str, Any]:
        from .llm.policy import lmstudio_live_voice_options

        return lmstudio_live_voice_options(user_message)

    def observe_live_voice_provider_stream(self, response: Any) -> Iterator[Any]:
        from .llm.stream import observe_live_voice_provider_stream

        yield from observe_live_voice_provider_stream(response)

    def new_text_chunker(self) -> Any:
        from .llm.stream import LowLatencyTextChunker

        return LowLatencyTextChunker()

    def new_request_gate(self) -> Any:
        from .llm.call_tools import RequestGate

        return RequestGate()


def create_live_voice_chat_port() -> LiveVoiceChatPort:
    return LiveVoiceChatIntegration()


__all__ = ["LiveVoiceChatIntegration", "create_live_voice_chat_port"]
