"""Compatibility facade for historically shared Omnix helpers.

New production code should import the owning module directly:
- settings/secrets: app.settings.access
- providers/audio providers: app.providers.service
- resource paths: app.runtime.paths
- legacy session callback bridge: app.chat.legacy_session_state
- image download state: app.image.download_state

This module intentionally contains no provider registry, persistence adapter,
settings document, or feature-specific execution logic.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.chat.legacy_session_state import (
    clear_legacy_session_callbacks,
    install_legacy_session_callbacks,
    load_sessions,
    save_sessions,
    update_sessions,
)
from app.settings.access import (
    load_secrets,
    load_settings,
    save_secrets,
    save_settings,
)
from app.config.defaults import DEFAULT_SETTINGS, DEFAULT_SYSTEM_PROMPT
from app.image.download_state import downloads
from app.providers.service import (
    get_global_system_prompt,
    get_provider,
    get_provider_config,
    get_stt_provider,
    get_tts_provider,
    invalidate_provider_cache,
)
from app.runtime.paths import (
    BASE_DIR,
    DATA_DIR,
    LOGO_DIR,
    LOGS_DIR,
    MODELS_DIR,
    RESOURCES_DIR,
    VOICE_CLONES_DIR,
    VOICE_CLONES_FILE,
)

TTS_SAMPLE_RATE = 24_000
TARGET_SR = TTS_SAMPLE_RATE
STT_BASE_URL = "http://127.0.0.1:5201"

# Retained path names for compatibility with old tests/importers. Production
# settings/secrets are not read from these files.
SETTINGS_FILE = str(Path(DATA_DIR) / "settings.json")
SECRETS_FILE = str(Path(DATA_DIR) / "secrets.json")
SESSIONS_FILE = str(Path(DATA_DIR) / "sessions.json")

# Deprecated mutable aliases. Image download state has a feature owner.
llamacpp_server_downloads: dict[str, Any] = {}


def _voice_inventory() -> dict[str, dict[str, Any]]:
    root = Path(VOICE_CLONES_DIR)
    if not root.exists():
        return {}
    return {
        path.stem: {
            "speaker": "default",
            "language": "en",
            "voice_clone_id": path.stem,
            "has_audio": True,
            "is_preloaded": True,
            "gender": "neutral",
        }
        for path in root.glob("*.wav")
    }


custom_voices = _voice_inventory()


def install_postgresql_document_callbacks(
    *,
    load_settings_callback=None,
    save_settings_callback=None,
    load_sessions_callback,
    save_sessions_callback,
    load_secrets_callback=None,
    save_secrets_callback=None,
    update_sessions_callback=None,
) -> None:
    """Deprecated compatibility wrapper.

    Settings/secrets callbacks are intentionally ignored because their authority
    moved to SettingsService/provider secret storage. Only the legacy session
    bridge remains installable.
    """
    del load_settings_callback, save_settings_callback
    del load_secrets_callback, save_secrets_callback
    install_legacy_session_callbacks(
        load_callback=load_sessions_callback,
        save_callback=save_sessions_callback,
        update_callback=update_sessions_callback,
    )


def clear_postgresql_document_callbacks() -> None:
    clear_legacy_session_callbacks()


def extract_thinking(content: str | None) -> tuple[str, str | None]:
    if not content:
        return "", content
    lines = content.split("\n")
    for index, line in enumerate(lines):
        lowered = line.strip().lower()
        if any(
            marker in lowered
            for marker in (
                "analyze",
                "identify the intent",
                "determine the answer",
                "formulate",
                "final output",
            )
        ):
            thinking = "\n".join(lines[:index]).strip()
            answer = "\n".join(lines[index:]).strip()
            if len(thinking) > 20:
                return thinking, answer
    return "", content


def remove_emojis(text: str) -> str:
    if not text:
        return text
    pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\u2702-\u27B0\u24C2-\U0001F251]+",
        flags=re.UNICODE,
    )
    return pattern.sub("", text)


def format_size(bytes_size: float) -> str:
    value = float(bytes_size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"
