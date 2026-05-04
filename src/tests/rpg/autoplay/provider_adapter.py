from __future__ import annotations

import inspect
import json
from typing import Any, Dict, List


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def describe_provider_shape(provider: Any) -> Dict[str, Any]:
    if provider is None:
        return {"type": "None", "methods": []}
    methods = []
    for name in dir(provider):
        if name.startswith("_"):
            continue
        value = getattr(provider, name, None)
        if not callable(value):
            continue
        signature = ""
        try:
            signature = str(inspect.signature(value))
        except Exception:
            signature = "<uninspectable>"
        methods.append({"name": name, "signature": signature})
    return {
        "type": type(provider).__name__,
        "module": type(provider).__module__,
        "repr": repr(provider)[:500],
        "methods": methods[:80],
        "attrs": [
            name
            for name in dir(provider)
            if not name.startswith("_")
            and not callable(getattr(provider, name, None))
        ][:80],
    }


def _extract_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "content", "response", "output", "message"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return message["content"]
                if isinstance(first.get("text"), str):
                    return first["text"]
    if isinstance(result, list) and result:
        return _extract_text(result[0])

    # App provider response objects, e.g. app.providers.base.ChatResponse.
    for attr in ("content", "text", "response", "output", "message"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.strip():
            return value

    # Some response wrappers expose .to_dict().
    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        try:
            return _extract_text(to_dict())
        except Exception:
            pass

    # Dataclass/pydantic-ish objects.
    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        try:
            return _extract_text(model_dump())
        except Exception:
            pass

    dict_method = getattr(result, "dict", None)
    if callable(dict_method):
        try:
            return _extract_text(dict_method())
        except Exception:
            pass

    return ""


def _call_with_supported_kwargs(method: Any, *args: Any, **kwargs: Any) -> Any:
    """Call provider method while tolerating different provider signatures."""
    try:
        signature = inspect.signature(method)
        supported = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
        return method(*args, **supported)
    except (TypeError, ValueError):
        # Some provider methods are C/proxy callables without inspectable signatures.
        try:
            return method(*args, **kwargs)
        except TypeError:
            return method(*args)


def _build_chat_messages(prompt: str) -> List[Any]:
    """Build chat messages in the app provider's preferred shape.

    LMStudioProvider.chat_completion expects app.providers.base.ChatMessage
    instances. If unavailable, fall back to OpenAI-style dicts.
    """
    try:
        from app.providers.base import ChatMessage

        return [ChatMessage(role="user", content=prompt)]
    except Exception:
        return [{"role": "user", "content": prompt}]


def call_provider_text(provider: Any, prompt: str, *, max_tokens: int = 600) -> str:
    """Compatibility wrapper for app LLM providers.

    Supports common shapes:
    - generate_text(prompt, ...)
    - complete(prompt, ...)
    - chat(messages, ...)
    - generate(prompt, ...)
    - invoke(prompt, ...)
    - __call__(prompt)
    - OpenAI-compatible .client.chat.completions.create(...)
    """
    if provider is None:
        raise RuntimeError("provider_missing")

    attempts: List[str] = []

    # Direct text methods.
    for method_name in (
        "generate_text",
        "complete",
        "generate",
        "invoke",
        "run",
        "ask",
        "call",
    ):
        method = getattr(provider, method_name, None)
        if callable(method):
            try:
                result = _call_with_supported_kwargs(
                    method,
                    prompt,
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                text = _extract_text(result)
                if text:
                    return text
                attempts.append(f"{method_name}:empty_text:{type(result).__name__}")
            except Exception as exc:
                attempts.append(f"{method_name}:{type(exc).__name__}:{exc}")

    # Chat-style methods.
    messages = _build_chat_messages(prompt)
    for method_name in ("chat_completion", "chat", "create_chat_completion"):
        method = getattr(provider, method_name, None)
        if callable(method):
            # Try keyword messages first, then positional messages, then raw prompt.
            for call_shape in ("keyword_messages", "positional_messages", "raw_prompt"):
                try:
                    if call_shape == "keyword_messages":
                        result = _call_with_supported_kwargs(
                            method,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=0.2,
                        )
                    elif call_shape == "positional_messages":
                        result = _call_with_supported_kwargs(
                            method,
                            messages,
                            max_tokens=max_tokens,
                            temperature=0.2,
                        )
                    else:
                        result = _call_with_supported_kwargs(
                            method,
                            prompt,
                            max_tokens=max_tokens,
                            temperature=0.2,
                        )
                    text = _extract_text(result)
                    if text:
                        return text
                    attempts.append(f"{method_name}/{call_shape}:empty_text:{type(result).__name__}")
                except Exception as exc:
                    attempts.append(f"{method_name}/{call_shape}:{type(exc).__name__}:{exc}")

    # OpenAI-compatible client object.
    client = getattr(provider, "client", None)
    try:
        completions = client.chat.completions
        create = completions.create
        model = (
            getattr(provider, "model", None)
            or getattr(provider, "model_name", None)
            or getattr(provider, "default_model", None)
        )
        openai_messages = []
        for message in messages:
            if isinstance(message, dict):
                openai_messages.append(message)
            else:
                to_dict = getattr(message, "to_dict", None)
                if callable(to_dict):
                    openai_messages.append(to_dict())
                else:
                    openai_messages.append(
                        {
                            "role": getattr(message, "role", "user"),
                            "content": getattr(message, "content", ""),
                        }
                    )
        kwargs: Dict[str, Any] = {
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if model:
            kwargs["model"] = model
        result = create(**kwargs)
        text = _extract_text(result)
        if text:
            return text
        attempts.append(f"client.chat.completions.create:empty_text:{type(result).__name__}")
    except Exception as exc:
        attempts.append(f"client.chat.completions.create:{type(exc).__name__}:{exc}")

    # Callable provider.
    if callable(provider):
        try:
            result = provider(prompt)
            text = _extract_text(result)
            if text:
                return text
            attempts.append(f"callable:empty_text:{type(result).__name__}")
        except Exception as exc:
            attempts.append(f"callable:{type(exc).__name__}:{exc}")

    shape = describe_provider_shape(provider)
    raise RuntimeError(
        "unsupported_provider_shape:"
        + type(provider).__name__
        + ":attempts="
        + " | ".join(attempts[-20:])
        + ":methods="
        + ",".join([row["name"] for row in shape.get("methods", [])[:40]])
    )


def dummy_json_provider_response(action: str) -> str:
    return json.dumps(
        {
            "format_version": "rpg_player_action_v1",
            "intent": "test action",
            "action": action,
            "reason": "dummy provider response",
            "risk": "low",
            "goal_id": "",
        },
        sort_keys=True,
    )