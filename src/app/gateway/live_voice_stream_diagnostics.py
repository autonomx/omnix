"""Structured diagnostics for live-call text and audio streaming."""
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.shared import LOGS_DIR

from .resilient_rotating_file_handler import ResilientRotatingFileHandler

LIVE_VOICE_STREAM_LOG_PATH = Path(LOGS_DIR) / "live-call-streaming.log"
LIVE_VOICE_STREAM_LOG_MAX_BYTES = 25_000_000
LIVE_VOICE_STREAM_LOG_BACKUP_COUNT = 4
_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")
_SEQUENCE = itertools.count(1)


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
    LIVE_VOICE_STREAM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = ResilientRotatingFileHandler(
        LIVE_VOICE_STREAM_LOG_PATH,
        maxBytes=LIVE_VOICE_STREAM_LOG_MAX_BYTES,
        backupCount=LIVE_VOICE_STREAM_LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=False,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    record_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(record_queue)
    logger = logging.getLogger("omnix.live_voice.streaming")
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
    return str(LIVE_VOICE_STREAM_LOG_PATH.resolve())


def normalize_trace_id(value: Any = None) -> str:
    """Return a bounded log-safe turn or controller correlation identifier."""
    candidate = _ID_PATTERN.sub("-", str(value or "")).strip("-._:")[:120]
    return candidate or "live-call-unscoped"


def live_voice_log(trace_id: str, source: str, event: str, **details: Any) -> None:
    """Queue one JSON-line live-call diagnostics record without blocking audio work."""
    if event == "delivery_checkpoint":
        _persist_delivery(details)
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "monotonic_ms": round(time.perf_counter_ns() / 1_000_000, 3),
        "sequence": next(_SEQUENCE),
        "trace_id": normalize_trace_id(trace_id),
        "source": str(source or "unknown")[:80],
        "event": str(event or "diagnostic")[:160],
        "process_id": os.getpid(),
        "thread_name": threading.current_thread().name,
        "thread_id": threading.get_ident(),
        **details,
    }
    try:
        _LOGGER.info(json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_default))
    except Exception:
        _LOGGER.exception(
            json.dumps(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "trace_id": normalize_trace_id(trace_id),
                    "source": "diagnostics",
                    "event": "serialization_failed",
                },
                sort_keys=True,
            )
        )


def _persist_delivery(details: dict[str, Any]) -> None:
    turn_id = str(details.get("assistant_turn_id") or "").strip()
    if not turn_id:
        return
    try:
        from app.chat.assistant_turns import default_assistant_turn_coordinator
        from app.chat.delivery_sync import sync_delivery_metadata

        active_index = details.get("audio_interrupted_phrase_index")
        record = default_assistant_turn_coordinator().record_delivery(
            turn_id,
            generated_phrase_count=_count(details.get("generated_phrase_count")),
            audio_delivered_phrase_count=_count(details.get("audio_delivered_phrase_count")),
            audio_interrupted_phrase_index=_count(active_index) if active_index is not None else None,
            audio_played_samples=_count(details.get("audio_played_samples")),
            visual_delivered_text_end=_count(details.get("visual_delivered_text_end")),
            context_delivered_text_end=_count(details.get("context_delivered_text_end")),
            delivery_policy="reveal_as_spoken",
        )
        if record is not None:
            sync_delivery_metadata(record)
    except Exception:
        return


def _count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


live_voice_log(
    "live-call-diagnostics",
    "diagnostics",
    "logger_ready",
    log_path=diagnostics_log_path(),
    max_bytes=LIVE_VOICE_STREAM_LOG_MAX_BYTES,
    backup_count=LIVE_VOICE_STREAM_LOG_BACKUP_COUNT,
)
