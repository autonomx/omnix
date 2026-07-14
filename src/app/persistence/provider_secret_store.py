"""OS-protected local storage for provider API keys.

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
_DESCRIPTION = "Omnix provider API keys"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


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
        _ = source_buffer  # Keep the input allocation alive through CryptProtectData.
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
        _ = source_buffer  # Keep the input allocation alive through CryptUnprotectData.
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def _stored_api_keys() -> dict[str, str]:
    path = provider_secret_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(_unprotect(path.read_bytes()).decode("utf-8"))
    except (OSError, UnicodeError, ValueError, LegacyPersistenceRetired):
        return {}
    if not isinstance(payload, dict):
        return {}
    api_keys = payload.get("api_keys")
    if not isinstance(api_keys, dict):
        return {}
    return {provider: str(api_keys.get(provider) or "") for provider in _PROVIDERS}


def load_provider_secrets() -> dict[str, Any]:
    api_keys = _stored_api_keys()
    for provider, environment_key in _ENVIRONMENT_KEYS.items():
        environment_value = os.environ.get(environment_key, "").strip()
        if environment_value:
            api_keys[provider] = environment_value
    return {"api_keys": {provider: api_keys.get(provider, "") for provider in _PROVIDERS}}


def save_provider_secrets(payload: dict[str, Any]) -> None:
    if sys.platform != "win32":
        raise LegacyPersistenceRetired("provider-key editing requires an operating-system credential store")
    incoming = payload.get("api_keys") if isinstance(payload, dict) else None
    incoming = incoming if isinstance(incoming, dict) else {}
    api_keys = _stored_api_keys()
    for provider, environment_key in _ENVIRONMENT_KEYS.items():
        if os.environ.get(environment_key, "").strip():
            continue
        value = str(incoming.get(provider) or "").strip()
        if value:
            api_keys[provider] = value
        else:
            api_keys.pop(provider, None)

    path = provider_secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = _protect(json.dumps({"api_keys": api_keys}, sort_keys=True).encode("utf-8"))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(protected)
    os.replace(temporary, path)
