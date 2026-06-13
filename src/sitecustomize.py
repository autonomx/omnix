"""Omnix Python startup compatibility hooks.

This module is imported automatically by Python when ``src`` is on the
interpreter path, which is the case for the local launch scripts. Keep this
file intentionally tiny and deterministic.
"""

from __future__ import annotations

import builtins


# Older/newer NPC initiative slices disagree on where ``opening_bonus`` is
# defined. The initiative module reads it as a global fallback in one idle
# candidate path; providing a builtins default prevents resume/idle catch-up
# from crashing while the owning module is normalized.
if not hasattr(builtins, "opening_bonus"):
    builtins.opening_bonus = 0.0
