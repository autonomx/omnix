"""Omnix-owned model transport for agent runtimes.

The endpoint is intentionally intelligence-only. It can invoke configured
BaseProvider implementations, but it cannot execute capabilities or widen a run's
authority. Requests are bound to an existing durable agent run and its ModelRef.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.providers.base import ChatMessage, ChatResponse
from app.shared import get_provider

from .service import default_agent_run_service

router = APIRouter(prefix="/api/agent-model/v1", tags=["agent-model"])

_STREAM_END = object()


def normalize_llm_provider_id(provider_id: str) -> str:
    value = str(provider_id or "").strip()
    return value.removeprefix("llm:") if value.startswith("llm:") else value


def normalize_llm_model_id(provider_id: str, model_id: str) -> str:
    provider = normalize_llm_provider_id(provider_id)
    value = str(model_id or "").strip()
    prefix = f"llm:{provider}:"
    return value[len(prefix):] if value.startswith(prefix) else value


def _next_stream_response(iterator: Any) -> Any:
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_END


class AgentModelMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: Any = ""
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class AgentChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[AgentModelMessage]
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = None


def _target_for_run(run_id: str, requested_model: str) -> tuple[str, str, str | None]:
    snapshot = default_agent_run_service().get(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    expected = f"{snapshot.spec.model.provider_id}::{snapshot.spec.model.model_id}"
    if requested_model != expected:
        raise HTTPException(status_code=403, detail="agent_model_outside_run_spec")
    return (
        normalize_llm_provider_id(snapshot.spec.model.provider_id),
        normalize_llm_model_id(
            snapshot.spec.model.provider_id,
            snapshot.spec.model.model_id,
        ),
        snapshot.spec.model.reasoning_effort,
    )


def _messages(rows: list[AgentModelMessage]) -> list[ChatMessage]:
    result: list[ChatMessage] = []
    for row in rows:
        content = row.content
        if isinstance(content, list):
            text_parts = [
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            content = "\n".join(part for part in text_parts if part)
        elif not isinstance(content, str):
            content = json.dumps(content, sort_keys=True, default=str)
        result.append(
            ChatMessage(
                role=row.role,
                content=content,
                name=row.name,
                tool_calls=row.tool_calls,
                tool_call_id=row.tool_call_id,
            )
        )
    return result


def _kwargs(request: AgentChatCompletionRequest, default_effort: str | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if request.tools is not None:
        values["tools"] = request.tools
    if request.tool_choice is not None:
        values["tool_choice"] = request.tool_choice
    if request.temperature is not None:
        values["temperature"] = request.temperature
    if request.max_tokens is not None:
        values["max_tokens"] = request.max_tokens
    effort = request.reasoning_effort or default_effort
    if effort:
        values["reasoning_effort"] = effort
    return values


def _choice(response: ChatResponse, *, delta: bool) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if response.content:
        body["content"] = response.content
    if response.tool_calls:
        body["tool_calls"] = response.tool_calls
    if response.thinking:
        body["reasoning_content"] = response.thinking
    elif response.reasoning:
        body["reasoning_content"] = response.reasoning
    return {
        "index": 0,
        "delta" if delta else "message": (
            body if delta else {"role": "assistant", **body}
        ),
        "finish_reason": response.finish_reason,
    }


@router.get("/models")
def list_agent_models(x_omnix_agent_run_id: str = Header(alias="X-Omnix-Agent-Run-Id")) -> dict[str, Any]:
    snapshot = default_agent_run_service().get(x_omnix_agent_run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="agent_run_not_found")
    key = f"{snapshot.spec.model.provider_id}::{snapshot.spec.model.model_id}"
    return {
        "object": "list",
        "data": [
            {
                "id": key,
                "object": "model",
                "owned_by": "omnix",
                "metadata": {
                    "provider_id": snapshot.spec.model.provider_id,
                    "model_id": snapshot.spec.model.model_id,
                },
            }
        ],
    }


@router.post("/chat/completions")
async def agent_chat_completion(
    request: AgentChatCompletionRequest,
    x_omnix_agent_run_id: str = Header(alias="X-Omnix-Agent-Run-Id"),
) -> Any:
    provider_id, model_id, default_effort = await asyncio.to_thread(
        _target_for_run,
        x_omnix_agent_run_id,
        request.model,
    )
    provider = await asyncio.to_thread(get_provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=503, detail=f"agent_provider_unavailable:{provider_id}")
    messages = _messages(request.messages)
    kwargs = _kwargs(request, default_effort)
    completion_id = f"chatcmpl-omnix-{x_omnix_agent_run_id[:16]}"
    created = int(time.time())

    if not request.stream:
        response = await asyncio.to_thread(
            provider.chat_completion,
            messages,
            model=model_id,
            stream=False,
            **kwargs,
        )
        if not isinstance(response, ChatResponse):
            raise HTTPException(status_code=502, detail="agent_provider_invalid_response")
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": request.model,
            "choices": [_choice(response, delta=False)],
            "usage": response.usage or {},
        }

    iterator = await asyncio.to_thread(
        provider.chat_completion,
        messages,
        model=model_id,
        stream=True,
        **kwargs,
    )

    async def generate():
        try:
            while True:
                response = await asyncio.to_thread(_next_stream_response, iterator)
                if response is _STREAM_END:
                    break
                if not isinstance(response, ChatResponse):
                    continue
                payload = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [_choice(response, delta=True)],
                }
                if response.usage:
                    payload["usage"] = response.usage
                yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            payload = {
                "error": {
                    "message": f"{type(exc).__name__}: {exc}"[:1000],
                    "type": "agent_model_error",
                }
            }
            yield f"data: {json.dumps(payload, sort_keys=True)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
