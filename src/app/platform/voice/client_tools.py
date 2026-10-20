"""The voice client tool port (Voice Studio Phase 7): what MCP clients and ``/api/voice/v1`` can call.

A tool is registered by the module that owns it: Voice Studio registers speak,
transcribe, list_voices, design_voice and isolate; dubbing registers
dub_status through this port, so the platform never imports the app
(ADR-0016). Registering a tool grants nothing: each needs its capability on the
caller's credential, and runs in the credential's workspace.
"""
from __future__ import annotations

from typing import Any, Protocol

from app.runtime.ports import Port


class VoiceClientTool(Protocol):
    name: str
    # The credential capability it needs (``voice.speak``, ``dub.status``, ...); empty: any credential.
    capability: str
    description: str
    # JSON Schema of its arguments (an MCP tool's inputSchema).
    input_schema: dict[str, Any]

    def call(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


VOICE_CLIENT_TOOLS: Port[VoiceClientTool] = Port("voice.client_tools", VoiceClientTool, "many")

__all__ = ["VOICE_CLIENT_TOOLS", "VoiceClientTool"]
