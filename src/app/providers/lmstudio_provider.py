"""LM Studio API client provider."""

import json
import logging
import threading
import time
from queue import Empty, Queue
from typing import Any, Dict, Iterator, List, Optional

import requests

from app.providers.base import BaseLLMProvider
from app.providers.models import ChatMessage, ChatResponse, ModelInfo
from app.providers.tracing import provider_call_enter, provider_call_exit

logger = logging.getLogger(__name__)

_DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_DEFAULT_STREAM_QUEUE_SIZE = 256
_STREAM_QUEUE_SENTINEL = object()


class LMStudioProvider(BaseLLMProvider):
    """Provider for LM Studio's OpenAI-compatible API."""

    def __init__(self, config):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:1234/v1"
        self.api_key = config.api_key or "lm-studio"
        self.default_model = config.default_model
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self._session = requests.Session()
        self._session.headers.update(self.headers)

    def test_connection(self) -> bool:
        try:
            response = self._session.get(
                f"{self.base_url}/models",
                timeout=self.config.timeout,
            )
            return response.status_code == 200
        except Exception as exc:
            logger.warning("LM Studio connection test failed: %s", exc)
            return False

    def list_models(self) -> List[ModelInfo]:
        try:
            response = self._session.get(
                f"{self.base_url}/models",
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("data", []):
                model_id = model.get("id")
                if model_id:
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=model_id,
                            provider=self.config.provider_name,
                        )
                    )
            return models
        except Exception as exc:
            logger.warning("Could not list LM Studio models: %s", exc)
            return []

    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        include_metrics: bool = False,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> ChatResponse | Iterator[ChatResponse]:
        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [message.model_dump() for message in messages],
            "stream": stream,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(self.config.extra_params)
        payload.update(kwargs)
        effective_timeout = timeout if timeout is not None else self.config.timeout
        trace_row = provider_call_enter(
            provider=self.config.provider_name,
            model=str(payload.get("model") or ""),
            operation="chat_completion",
            stream=stream,
        )
        try:
            result = (
                self._stream_completion(
                    payload,
                    include_metrics=include_metrics,
                    timeout=effective_timeout,
                )
                if stream
                else self._non_stream_completion(
                    payload,
                    include_metrics=include_metrics,
                    timeout=effective_timeout,
                )
            )
            provider_call_exit(trace_row, ok=True)
            return result
        except Exception as exc:
            provider_call_exit(trace_row, ok=False, error=f"{type(exc).__name__}: {exc}")
            raise

    def _make_chat_completion_request(
        self,
        payload: Dict[str, Any],
        *,
        stream: bool,
        include_metrics: bool,
        timeout: float | None,
    ):
        request_payload = dict(payload)
        if include_metrics:
            request_payload["stream_options"] = {"include_usage": True}
        response = self._session.post(
            f"{self.base_url}/chat/completions",
            json=request_payload,
            stream=stream,
            timeout=timeout,
        )
        response.raise_for_status()
        return response

    def _non_stream_completion(
        self,
        payload: Dict[str, Any],
        *,
        include_metrics: bool = False,
        timeout: float | None = None,
    ) -> ChatResponse:
        response = self._make_chat_completion_request(
            payload,
            stream=False,
            include_metrics=include_metrics,
            timeout=timeout,
        )
        max_response_bytes = max(
            1,
            int(
                self.config.extra_params.get("max_response_bytes")
                or _DEFAULT_MAX_RESPONSE_BYTES
            ),
        )
        headers = getattr(response, "headers", {}) or {}
        try:
            declared_length = int(headers.get("content-length") or 0)
        except (AttributeError, TypeError, ValueError):
            declared_length = 0
        if declared_length > max_response_bytes:
            raise ConnectionError(
                "LM Studio response exceeds configured byte limit: "
                f"{declared_length}>{max_response_bytes}"
            )
        content = getattr(response, "content", b"") or b""
        if len(content) > max_response_bytes:
            raise ConnectionError(
                "LM Studio response exceeds configured byte limit: "
                f"{len(content)}>{max_response_bytes}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectionError(f"Invalid JSON response: {exc}") from exc
        choices = data.get("choices", [])
        if not choices:
            raise ConnectionError("No choices in response")
        message = choices[0].get("message", {})
        thinking = message.get("reasoning") or message.get("thinking")
        tool_calls = message.get("tool_calls")
        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", payload.get("model", "")),
            usage=data.get("usage"),
            thinking=thinking,
            reasoning=thinking,
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            finish_reason=choices[0].get("finish_reason"),
            raw_response=data,
        )

    def _stream_completion(
        self,
        payload: Dict[str, Any],
        *,
        include_metrics: bool = False,
        timeout: float | None = None,
    ) -> Iterator[ChatResponse]:
        response = self._make_chat_completion_request(
            payload,
            stream=True,
            include_metrics=include_metrics,
            timeout=timeout,
        )
        max_queue_size = max(
            1,
            int(
                self.config.extra_params.get("stream_queue_size")
                or _DEFAULT_STREAM_QUEUE_SIZE
            ),
        )
        event_queue: Queue[object] = Queue(maxsize=max_queue_size)
        stop_event = threading.Event()

        def read_events() -> None:
            try:
                for raw_line in response.iter_lines(decode_unicode=True):
                    if stop_event.is_set():
                        return
                    if not raw_line:
                        continue
                    line = raw_line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        decoded = json.loads(data)
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed LM Studio stream event")
                        continue
                    while not stop_event.is_set():
                        try:
                            event_queue.put(decoded, timeout=0.1)
                            break
                        except Exception:
                            continue
            except Exception as exc:
                if not stop_event.is_set():
                    event_queue.put(exc)
            finally:
                event_queue.put(_STREAM_QUEUE_SENTINEL)

        reader = threading.Thread(target=read_events, daemon=True)
        reader.start()
        try:
            while True:
                try:
                    event = event_queue.get(timeout=max(1.0, float(timeout or 60.0)))
                except Empty as exc:
                    raise TimeoutError("LM Studio stream timed out") from exc
                if event is _STREAM_QUEUE_SENTINEL:
                    break
                if isinstance(event, Exception):
                    raise event
                if not isinstance(event, dict):
                    continue
                choices = event.get("choices") or []
                usage = event.get("usage")
                if not choices:
                    if usage:
                        yield ChatResponse(
                            content="",
                            model=event.get("model", payload.get("model", "")),
                            usage=usage,
                            raw_response=event,
                        )
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                thinking = delta.get("reasoning") or delta.get("thinking")
                tool_calls = delta.get("tool_calls")
                yield ChatResponse(
                    content=delta.get("content", ""),
                    model=event.get("model", payload.get("model", "")),
                    usage=usage,
                    thinking=thinking,
                    reasoning=thinking,
                    tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                    finish_reason=choice.get("finish_reason"),
                    raw_response=event,
                )
        finally:
            stop_event.set()
            try:
                response.close()
            except Exception:
                pass
            reader.join(timeout=1.0)

    def close(self) -> None:
        self._session.close()
