"""Generative UI for chat replies: a typed block catalog compiled from fenced JSON.

The model writes ```omnix-ui fences holding one JSON object each. The compiler
validates them against ``CATALOG``, normalizes them and stores the result on
the reply as ``metadata.ui`` with text and speech projections. Nothing the
model writes is executed; React renders the validated specs.
"""
from __future__ import annotations

from .catalog import CATALOG, ChatUiDiagnostic, ChatUiPayload, ChatUiSegment
from .compiler import COMPILER_VERSION, CompileScope, compile_chat_ui, has_ui_fence, rebase_ui_after_rewrite
from .finalize import attach_reply_ui, finalize_reply_ui

__all__ = [
    "CATALOG",
    "COMPILER_VERSION",
    "ChatUiDiagnostic",
    "ChatUiPayload",
    "ChatUiSegment",
    "CompileScope",
    "attach_reply_ui",
    "compile_chat_ui",
    "finalize_reply_ui",
    "has_ui_fence",
    "rebase_ui_after_rewrite",
]
