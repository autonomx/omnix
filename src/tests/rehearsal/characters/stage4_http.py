"""HTTP transport for the Character Mode Stage 4 shared-memory pilot."""
from __future__ import annotations

from typing import Any, Protocol

from .stage3_http import HttpStage3Gateway, Stage3Gateway


class Stage4Gateway(Stage3Gateway, Protocol):
    def update_character(self, character_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class HttpStage4Gateway(HttpStage3Gateway):
    pass


__all__ = ["HttpStage4Gateway", "Stage4Gateway"]
