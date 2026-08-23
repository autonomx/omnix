"""OS-protected local storage for provider API keys and trading credentials.

Provider credentials must not be stored in PostgreSQL or the settings document.
On Windows, DPAPI provides a user-scoped encrypted store suitable for the local
Omnix process. Explicit process-environment values remain authoritative.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .runtime import LegacyPersistenceRetired

_PROVIDERS = ("openrouter", "cerebras")
_ENVIRONMENT_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}
_RESEARCH_PROVIDERS = ("brave", "tavily")
_RESEARCH_ENVIRONMENT_KEYS: dict[str, tuple[str, ...]] = {
    "brave": ("OMNIX_BRAVE_SEARCH_API_KEY", "BRAVE_SEARCH_API_KEY"),
    "tavily": ("OMNIX_TAVILY_SEARCH_API_KEY", "TAVILY_API_KEY"),
}
_LEGACY_RESEARCH_ENVIRONMENT_KEY = "OMNIX_WEB_SEARCH_API_KEY"
_LEGACY_RESEARCH_PROVIDER_ENVIRONMENT_KEY = "OMNIX_WEB_SEARCH_PROVIDER"
_TRADING_PROVIDERS = ("alpaca_iex", "coinmarketcap")
_TRADING_ENVIRONMENT_KEYS: dict[str, dict[str, tuple[str, ...]]] = {
    "alpaca_iex": {
        "api_key_id": ("OMNIX_ALPACA_API_KEY_ID", "APCA_API_KEY_ID"),
        "secret_key": ("OMNIX_ALPACA_API_SECRET_KEY", "APCA_API_SECRET_KEY"),
    },
    "coinmarketcap": {
        "api_key": ("COINMARKETCAP_API_KEY", "CMC_PRO_API_KEY"),
    },
}
_DESCRIPTION = "Omnix provider API keys"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01
_ENVIRONMENT_OWNED_MARKER = b"OMNIX_ENVIRONMENT_OWNED_PROVIDER_KEYS\n"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def provider_secret_path() -> Path:
    configured = os.environ.get("OMNIX_PROVIDER_SECRETS_PATH", "").strip()
    if configured:
        return Path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    return Path(local_app_data) / "Omnix" / "secrets" / "provider-api-keys.dpapi"


def _input_blob(value: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(value)
    blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _protect(value: bytes) -> bytes:
    if sys.platform != "win32":
        raise LegacyPersistenceRetired("provider-key editing requires an operating-system credential store")
    source, source_buffer = _input_blob(value)
    result = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        _DESCRIPTION,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(result),
    ):
        raise ctypes.WinError()
    try:
        _ = source_buffer
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def _unprotect(value: bytes) -> bytes:
    if sys.platform != "win32":
        raise LegacyPersistenceRetired("provider-key editing requires an operating-system credential store")
    source, source_buffer = _input_blob(value)
    result = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(result),
    ):
        raise ctypes.WinError()
    try:
        _ = source_buffer
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def _stored_payload() -> dict[str, Any]:
    path = provider_secret_path()
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    if raw == _ENVIRONMENT_OWNED_MARKER:
        return {}
    try:
        payload = json.loads(_unprotect(raw).decode("utf-8"))
    except (OSError, UnicodeError, ValueError, LegacyPersistenceRetired):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_payload(payload: dict[str, Any]) -> None:
    path = provider_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = _protect(json.dumps(payload, sort_keys=True).encode("utf-8"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(protected)
    os.replace(temporary, path)


def _stored_api_keys() -> dict[str, str]:
    api_keys = _stored_payload().get("api_keys")
    if not isinstance(api_keys, dict):
        return {}
    return {provider: str(api_keys.get(provider) or "") for provider in _PROVIDERS}


def _stored_research_api_keys() -> dict[str, str]:
    api_keys = _stored_payload().get("research_api_keys")
    if not isinstance(api_keys, dict):
        return {}
    return {provider: str(api_keys.get(provider) or "") for provider in _RESEARCH_PROVIDERS}


def _stored_trading_credentials() -> dict[str, dict[str, str]]:
    credentials = _stored_payload().get("trading_credentials")
    if not isinstance(credentials, dict):
        return {}
    output: dict[str, dict[str, str]] = {}
    for provider in _TRADING_PROVIDERS:
        raw = credentials.get(provider)
        if not isinstance(raw, dict):
            continue
        output[provider] = {
            field: str(raw.get(field) or "")
            for field in _TRADING_ENVIRONMENT_KEYS[provider]
        }
    return output


def _first_environment_value(keys: tuple[str, ...]) -> str:
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _research_environment_value(provider: str) -> str:
    keys = _RESEARCH_ENVIRONMENT_KEYS.get(provider)
    return _first_environment_value(keys) if keys else ""


def _legacy_research_environment_value() -> str:
    return os.environ.get(_LEGACY_RESEARCH_ENVIRONMENT_KEY, "").strip()


def _legacy_research_provider() -> str:
    provider = os.environ.get(_LEGACY_RESEARCH_PROVIDER_ENVIRONMENT_KEY, "brave").strip().lower()
    return provider if provider in _RESEARCH_PROVIDERS else "brave"


def load_provider_secrets() -> dict[str, Any]:
    api_keys = _stored_api_keys()
    for provider, environment_key in _ENVIRONMENT_KEYS.items():
        environment_value = os.environ.get(environment_key, "").strip()
        if environment_value:
            api_keys[provider] = environment_value
    return {"api_keys": {provider: api_keys.get(provider, "") for provider in _PROVIDERS}}


def load_research_provider_secrets() -> dict[str, str]:
    """Return independent search-provider credentials without exposing them to settings JSON.

    Provider-specific environment variables are authoritative. The legacy shared
    ``OMNIX_WEB_SEARCH_API_KEY`` remains a compatibility fallback for exactly one
    provider selected by ``OMNIX_WEB_SEARCH_PROVIDER`` (Brave when unspecified).
    """

    api_keys = _stored_research_api_keys()
    legacy_value = _legacy_research_environment_value()
    legacy_provider = _legacy_research_provider()
    for provider in _RESEARCH_PROVIDERS:
        environment_value = _research_environment_value(provider)
        if environment_value:
            api_keys[provider] = environment_value
        elif legacy_value and provider == legacy_provider:
            api_keys[provider] = legacy_value
        else:
            api_keys.setdefault(provider, "")
    return {provider: api_keys.get(provider, "") for provider in _RESEARCH_PROVIDERS}


def research_provider_credential_source(provider: str) -> str:
    if provider not in _RESEARCH_ENVIRONMENT_KEYS:
        raise ValueError("unsupported_research_provider")
    if _research_environment_value(provider):
        return "environment"
    if _legacy_research_environment_value() and provider == _legacy_research_provider():
        return "legacy_environment"
    if _stored_research_api_keys().get(provider):
        return "os_protected_store"
    return "missing"


def research_provider_credential_editable(provider: str) -> bool:
    if provider not in _RESEARCH_ENVIRONMENT_KEYS:
        raise ValueError("unsupported_research_provider")
    source = research_provider_credential_source(provider)
    return sys.platform == "win32" and source not in {"environment", "legacy_environment"}


def load_trading_provider_secrets() -> dict[str, dict[str, str]]:
    """Return trading credentials with process-environment values authoritative."""

    credentials = _stored_trading_credentials()
    for provider in _TRADING_PROVIDERS:
        current = dict(credentials.get(provider) or {})
        for field, environment_keys in _TRADING_ENVIRONMENT_KEYS[provider].items():
            environment_value = _first_environment_value(environment_keys)
            if environment_value:
                current[field] = environment_value
            else:
                current.setdefault(field, "")
        credentials[provider] = current
    return credentials


def trading_provider_credential_sources(provider: str) -> dict[str, str]:
    if provider not in _TRADING_ENVIRONMENT_KEYS:
        raise ValueError("unsupported_trading_provider")
    stored = _stored_trading_credentials().get(provider, {})
    sources: dict[str, str] = {}
    for field, environment_keys in _TRADING_ENVIRONMENT_KEYS[provider].items():
        if _first_environment_value(environment_keys):
            sources[field] = "environment"
        elif stored.get(field):
            sources[field] = "os_protected_store"
        else:
            sources[field] = "missing"
    return sources


def _save_environment_owned_marker(incoming: dict[str, Any]) -> None:
    for provider, environment_key in _ENVIRONMENT_KEYS.items():
        requested = str(incoming.get(provider) or "").strip()
        if requested and not os.environ.get(environment_key, "").strip():
            raise LegacyPersistenceRetired(
                "provider-key editing requires an operating-system credential store"
            )
    path = provider_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_ENVIRONMENT_OWNED_MARKER)
    os.replace(temporary, path)


def save_provider_secrets(payload: dict[str, Any]) -> None:
    incoming = payload.get("api_keys") if isinstance(payload, dict) else None
    incoming = incoming if isinstance(incoming, dict) else {}
    if sys.platform != "win32":
        _save_environment_owned_marker(incoming)
        return

    stored_payload = _stored_payload()
    api_keys = _stored_api_keys()
    for provider, environment_key in _ENVIRONMENT_KEYS.items():
        if os.environ.get(environment_key, "").strip():
            continue
        value = str(incoming.get(provider) or "").strip()
        if value:
            api_keys[provider] = value
        else:
            api_keys.pop(provider, None)
    stored_payload["api_keys"] = api_keys
    _write_payload(stored_payload)


def save_research_provider_secret(provider: str, value: str | None) -> None:
    """Persist one Brave/Tavily key in the user-scoped protected store.

    Environment-owned credentials cannot be overwritten from the UI. On non-Windows
    runtimes, UI editing fails closed while environment configuration remains supported.
    """

    if provider not in _RESEARCH_ENVIRONMENT_KEYS:
        raise ValueError("unsupported_research_provider")
    requested = str(value or "").strip()
    legacy_owned = (
        bool(_legacy_research_environment_value())
        and provider == _legacy_research_provider()
    )
    if _research_environment_value(provider) or legacy_owned:
        return
    if sys.platform != "win32":
        if requested:
            raise LegacyPersistenceRetired(
                "research credential editing requires an operating-system credential store"
            )
        return

    stored_payload = _stored_payload()
    api_keys = _stored_research_api_keys()
    if requested:
        api_keys[provider] = requested
    else:
        api_keys.pop(provider, None)
    stored_payload["research_api_keys"] = api_keys
    _write_payload(stored_payload)


def save_trading_provider_secrets(
    provider: str,
    updates: dict[str, str | None],
) -> None:
    """Persist partial trading-credential updates in the OS-protected store.

    Environment-owned fields cannot be overwritten from the UI. On non-Windows
    runtimes the UI store is unavailable; environment values remain supported.
    """

    if provider not in _TRADING_ENVIRONMENT_KEYS:
        raise ValueError("unsupported_trading_provider")
    allowed_fields = set(_TRADING_ENVIRONMENT_KEYS[provider])
    unknown = set(updates).difference(allowed_fields)
    if unknown:
        raise ValueError(f"unsupported_trading_credential_field:{sorted(unknown)[0]}")

    if sys.platform != "win32":
        for field, value in updates.items():
            requested = str(value or "").strip()
            environment_value = _first_environment_value(
                _TRADING_ENVIRONMENT_KEYS[provider][field]
            )
            if requested and not environment_value:
                raise LegacyPersistenceRetired(
                    "trading credential editing requires an operating-system credential store"
                )
        return

    stored_payload = _stored_payload()
    all_credentials = stored_payload.get("trading_credentials")
    all_credentials = dict(all_credentials) if isinstance(all_credentials, dict) else {}
    current = dict(all_credentials.get(provider) or {})
    for field, value in updates.items():
        if _first_environment_value(_TRADING_ENVIRONMENT_KEYS[provider][field]):
            continue
        clean = str(value or "").strip()
        if clean:
            current[field] = clean
        else:
            current.pop(field, None)
    if current:
        all_credentials[provider] = current
    else:
        all_credentials.pop(provider, None)
    stored_payload["trading_credentials"] = all_credentials
    _write_payload(stored_payload)
