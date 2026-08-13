"""Structured diagnostics for chat TTS streaming."""
from __future__ import annotations

import atexit
import itertools
import json
import logging
import logging.handlers
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.shared import LOGS_DIR

from .content_free_diagnostics import sanitize_content_free_details
from .resilient_rotating_file_handler import ResilientRotatingFileHandler

TTS_STREAM_LOG_PATH = Path(LOGS_DIR) / "tts-streaming.log"
TTS_STREAM_LOG_MAX_BYTES = 25_000_000
TTS_STREAM_LOG_BACKUP_COUNT = 4
_STREAM_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_SEQUENCE = itertools.count(1)
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_STREAMS: dict[str, float] = {}


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _create_logger() -> tuple[logging.Logger, logging.handlers.QueueListener]:
    TTS_STREAM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = ResilientRotatingFileHandler(
        TTS_STREAM_LOG_PATH,
        maxBytes=TTS_STREAM_LOG_MAX_BYTES,
        backupCount=TTS_STREAM_LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=False,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    record_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(record_queue)
    logger = logging.getLogger("omnix.tts.streaming")
    logger.handlers.clear()
    logger.addHandler(queue_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    listener = logging.handlers.QueueListener(record_queue, file_handler, respect_handler_level=True)
    listener.start()
    return logger, listener


_LOGGER, _LISTENER = _create_logger()
atexit.register(_LISTENER.stop)


def diagnostics_log_path() -> str:
    """Return the absolute persistent diagnostics path."""
    return str(TTS_STREAM_LOG_PATH.resolve())


def normalize_stream_id(value: Any = None) -> str:
    """Return a bounded log-safe stream correlation identifier."""
    candidate = _STREAM_ID_PATTERN.sub("-", str(value or "")).strip("-._")[:80]
    return candidate or f"tts-{uuid.uuid4().hex}"


def stream_log(stream_id: str, source: str, event: str, **details: Any) -> None:
    """Queue one content-free JSON-line record without blocking audio work."""
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "monotonic_ms": round(time.perf_counter_ns() / 1_000_000, 3),
        "sequence": next(_SEQUENCE),
        "stream_id": stream_id,
        "source": source,
        "event": event,
        "process_id": os.getpid(),
        "thread_name": threading.current_thread().name,
        "thread_id": threading.get_ident(),
        **sanitize_content_free_details(details),
    }
    try:
        _LOGGER.info(json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_default))
    except Exception:
        _LOGGER.exception(
            json.dumps(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "stream_id": stream_id,
                    "source": "diagnostics",
                    "event": "serialization_failed",
                },
                sort_keys=True,
            )
        )


def active_streams_snapshot() -> dict[str, float]:
    """Return current stream IDs and ages without exposing request text."""
    now = time.perf_counter()
    with _ACTIVE_LOCK:
        return {
            active_id: round((now - started_at) * 1000, 3)
            for active_id, started_at in sorted(_ACTIVE_STREAMS.items())
        }


def begin_stream(stream_id: str, **details: Any) -> int:
    """Register a live stream and log overlap information."""
    now = time.perf_counter()
    with _ACTIVE_LOCK:
        previous = {
            active_id: round((now - started_at) * 1000, 3)
            for active_id, started_at in _ACTIVE_STREAMS.items()
        }
        _ACTIVE_STREAMS[stream_id] = now
        active_count = len(_ACTIVE_STREAMS)
    stream_log(
        stream_id,
        "server",
        "stream_registered",
        active_stream_count=active_count,
        preexisting_active_streams=previous,
        **details,
    )
    return active_count


def end_stream(stream_id: str, **details: Any) -> int:
    """Unregister a stream and record its lifetime and remaining overlap."""
    now = time.perf_counter()
    with _ACTIVE_LOCK:
        started_at = _ACTIVE_STREAMS.pop(stream_id, None)
        remaining = {
            active_id: round((now - active_started_at) * 1000, 3)
            for active_id, active_started_at in _ACTIVE_STREAMS.items()
        }
        active_count = len(_ACTIVE_STREAMS)
    stream_log(
        stream_id,
        "server",
        "stream_unregistered",
        active_stream_count=active_count,
        stream_lifetime_ms=round((now - started_at) * 1000, 3) if started_at is not None else None,
        remaining_active_streams=remaining,
        **details,
    )
    return active_count


stream_log(
    "diagnostics",
    "diagnostics",
    "logger_ready",
    log_path=diagnostics_log_path(),
    max_bytes=TTS_STREAM_LOG_MAX_BYTES,
    backup_count=TTS_STREAM_LOG_BACKUP_COUNT,
)
