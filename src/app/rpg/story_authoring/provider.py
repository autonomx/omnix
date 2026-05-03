from __future__ import annotations

from typing import Any, Dict


def _extract_text_from_provider_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "content", "response", "message"):
            value = result.get(key)
            if isinstance(value, str):
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
    return str(result)


def call_story_authoring_provider(
    app_context: Any,
    *,
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    if app_context is None:
        return {
            "ok": False,
            "reason": "missing_app_context",
            "text": "",
            "provider": "",
            "model": "",
        }
    get_provider = getattr(app_context, "get_provider", None)
    if not callable(get_provider):
        return {
            "ok": False,
            "reason": "missing_get_provider",
            "text": "",
            "provider": "",
            "model": "",
        }
    provider = get_provider()
    if provider is None:
        return {
            "ok": False,
            "reason": "provider_unavailable",
            "text": "",
            "provider": "",
            "model": "",
        }

    provider_name = str(getattr(provider, "name", "") or getattr(provider, "provider_name", "") or "")
    model_name = str(getattr(provider, "model", "") or getattr(provider, "model_name", "") or "")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if hasattr(provider, "chat") and callable(provider.chat):
            result = provider.chat(messages=messages)
        elif hasattr(provider, "complete") and callable(provider.complete):
            result = provider.complete(system_prompt + "\n\n" + user_prompt)
        elif hasattr(provider, "generate") and callable(provider.generate):
            result = provider.generate(system_prompt + "\n\n" + user_prompt)
        else:
            return {
                "ok": False,
                "reason": "provider_has_no_supported_call_method",
                "text": "",
                "provider": provider_name,
                "model": model_name,
            }
    except Exception as exc:
        return {
            "ok": False,
            "reason": f"provider_error:{type(exc).__name__}",
            "error": str(exc),
            "text": "",
            "provider": provider_name,
            "model": model_name,
        }

    return {
        "ok": True,
        "reason": "provider_called",
        "text": _extract_text_from_provider_result(result),
        "provider": provider_name,
        "model": model_name,
    }