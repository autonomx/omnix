"""Structured local diagnostics for character voice resolution.

The browser already persists live-call controller events to
``resources/logs/live-call-streaming.log``. This module adds small JSON-line
logs for the backend-to-TTS handoff and the standalone TTS process without
recording synthesized text.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
import logging.handlers
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.shared import LOGS_DIR

VOICE_DEBUG_LOG_MAX_BYTES = 10_000_000
VOICE_DEBUG_LOG_BACKUP_COUNT = 3
_CHANNEL_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_SEQUENCE = itertools.count(1)
_LOGGER_LOCK = threading.Lock()
_LOGGERS: dict[str, logging.Logger] = {}


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    return str(value)


def _safe_channel(channel: str) -> str:
    normalized = _CHANNEL_PATTERN.sub("-", str(channel or "voice")).strip("-._")
    return normalized[:60] or "voice"


def _log_dir() -> Path:
    configured = os.environ.get("OMNIX_VOICE_DEBUG_LOG_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path(LOGS_DIR)


def voice_debug_log_path(channel: str) -> str:
    """Return the absolute log path for one diagnostic process/channel."""
    return str((_log_dir() / f"voice-debug-{_safe_channel(channel)}.log").resolve())


def _logger(channel: str) -> logging.Logger:
    safe_channel = _safe_channel(channel)
    with _LOGGER_LOCK:
        existing = _LOGGERS.get(safe_channel)
        if existing is not None:
            return existing
        path = Path(voice_debug_log_path(safe_channel))
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path,
            maxBytes=VOICE_DEBUG_LOG_MAX_BYTES,
            backupCount=VOICE_DEBUG_LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=False,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger(f"omnix.voice_debug.{safe_channel}.{os.getpid()}")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _LOGGERS[safe_channel] = logger
        return logger


def text_fingerprint(text: str) -> str:
    """Return a non-reversible short fingerprint for correlating TTS requests."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def voice_debug_log(
    channel: str,
    event: str,
    *,
    trace_id: str = "",
    **details: Any,
) -> None:
    """Append one JSON diagnostic record without persisting speech content."""
    if os.environ.get("OMNIX_VOICE_DEBUG_LOGGING", "1").strip().lower() in {"0", "false", "off", "no"}:
        return
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "monotonic_ms": round(time.perf_counter_ns() / 1_000_000, 3),
        "sequence": next(_SEQUENCE),
        "channel": _safe_channel(channel),
        "event": str(event or "diagnostic")[:160],
        "trace_id": str(trace_id or "")[:180],
        "process_id": os.getpid(),
        "thread_name": threading.current_thread().name,
        "thread_id": threading.get_ident(),
        **details,
    }
    try:
        serialized = json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_default)
        _logger(channel).info(serialized)
    except (OSError, TypeError, ValueError):
        # Diagnostics must never interrupt speech generation or playback.
        return