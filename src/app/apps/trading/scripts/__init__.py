"""Omnix Scripts (TVP-11): a Pine Script-compatible subset, interpreted on the server.

``parse_script`` reads a script into a syntax tree, ``compile_script`` turns it into a program, and ``run_script``
runs the program bar by bar over a ``BarSeries``. The supported subset is described in
``docs/trading/OMNIX_SCRIPTS_SPEC.md``.
"""

from __future__ import annotations

from .errors import ScriptError, ScriptLimitError, ScriptSyntaxError, ScriptUnsupportedError
from .parser import parse_script
from .runtime import ScriptLimits, ScriptResult, ScriptRun, compile_script, run_script

__all__ = [
    "ScriptError",
    "ScriptLimitError",
    "ScriptLimits",
    "ScriptResult",
    "ScriptRun",
    "ScriptSyntaxError",
    "ScriptUnsupportedError",
    "compile_script",
    "parse_script",
    "run_script",
]
