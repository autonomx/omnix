"""What other modules may import from Dubbing (ADR-0016): its DTOs."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DubSegment(BaseModel):
    """One line: what was said, its translation, its take and whether a person approved them."""

    id: str
    position: int
    speaker: str
    start_seconds: float
    end_seconds: float
    budget_seconds: float = 0.0
    source_text: str
    translation: str = ""
    translation_revision: int = 0
    # llm, shortened (by the fitter) or person.
    translation_origin: str = ""
    voice_override: str = ""
    take_asset_id: str = ""
    take_revision: int = 0
    take_seconds: float = 0.0
    # pending, fits, stretched, shortened, over or short.
    fit_status: str = "pending"
    fit_ratio: float = 0.0
    shortenings: int = 0
    # The take was rendered from the current words.
    take_current: bool = False
    # A person approved the current words and this take.
    approved: bool = False


class DubProject(BaseModel):
    id: str
    title: str
    source_asset_id: str
    source_language: str
    target_language: str
    translator: str = ""
    engine: str = ""
    speakers: int = 0
    duration_seconds: float = 0.0
    steps: dict[str, Any] = Field(default_factory=dict)
    assets: dict[str, str] = Field(default_factory=dict)
    casting: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    line_count: int = 0
    approved_count: int = 0
    segments: list[DubSegment] = Field(default_factory=list)
