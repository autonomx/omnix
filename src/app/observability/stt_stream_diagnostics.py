"""Persistent content-free diagnostics for the live speech recognition service.

What the recognizer received and returned, per connection and segment: the half
of a lost turn the browser cannot see. Records never hold transcript text; the
shared sanitizer is the final boundary before disk.
"""
from __future__ import annotations

import atexit
import itertools
import json
import logging
import logging.handlers
import os
import queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.content_free_diagnostics import sanitize_content_free_details
from app.observability.resilient_rotating_file_handler import ResilientRotatingFileHandler
from app.runtime.paths import LOGS_DIR

STT_STREAM_LOG_PATH = Path(LOGS_DIR) / "stt-streaming.log"
STT_STREAM_LOG_MAX_BYTES = 25_000_000
STT_STREAM_LOG_BACKUP_COUNT = 4
_SEQUENCE = itertools.count(1)


def _create_logger() -> tuple[logging.Logger, logging.handlers.QueueListener]:
    STT_STREAM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Delayed: only the process that serves live recognition should create the file.
    file_handler = ResilientRotatingFileHandler(
        STT_STREAM_LOG_PATH,
        maxBytes=STT_STREAM_LOG_MAX_BYTES,
        backupCount=STT_STREAM_LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    record_queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
    stream_logger = logging.getLogger("omnix.stt.streaming")
    stream_logger.handlers.clear()
    stream_logger.addHandler(logging.handlers.QueueHandler(record_queue))
    stream_logger.setLevel(logging.INFO)
    stream_logger.propagate = False
    listener = logging.handlers.QueueListener(record_queue, file_handler, respect_handler_level=True)
    listener.start()
    return stream_logger, listener


_LOGGER, _LISTENER = _create_logger()
atexit.register(_LISTENER.stop)


def stt_stream_log(event: str, **details: Any) -> None:
    """Queue one content-free JSON-line record without blocking recognition."""
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "sequence": next(_SEQUENCE),
        "event": event,
        "process_id": os.getpid(),
        **sanitize_content_free_details(details),
    }
    _LOGGER.info(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))
