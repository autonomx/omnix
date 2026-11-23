"""Tombstone of the retired module live-speech (PA-4.3), written by scripts/retire_module.py on 2026-11-22.

Kernel-only, read by convention: the migrations next to it stay known, its
tables are owned by ``retired:live-speech``, recovery fails its job types once,
and its settings section keeps stored values. A later settings migration may
drop the section.
"""
from __future__ import annotations

MODULE_ID = "live-speech"
JOB_TYPES: tuple[str, ...] = ()
# (consumer, aggregate types, event type pattern)
OUTBOX_CONSUMERS: tuple[tuple[str, tuple[str, ...], str], ...] = ()
TOOL_IDS: tuple[str, ...] = ()
CAPABILITY_IDS: tuple[str, ...] = ()
