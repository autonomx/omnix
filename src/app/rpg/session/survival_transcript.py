from __future__ import annotations

"""Compatibility facade for N125.2 survival transcript projection.

The implementation now lives in smaller focused modules:

- ``survival_transcript_sources``: source/evidence classification helpers.
- ``survival_transcript_projector``: transcript row projection helpers.

Keep this module so older imports continue to work while future changes stay in
smaller files.
"""

from app.rpg.session.survival_transcript_projector import (  # noqa: F401
    persist_survival_evidence_into_transcript_row,
    persist_survival_evidence_into_transcript_rows,
)
from app.rpg.session.survival_transcript_sources import (  # noqa: F401
    COMPACTED_CONTRACT_CLIMATE_SOURCE,
    COMPACTED_FINAL_ROW_CLIMATE_SOURCE,
    SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT,
    has_need_values,
    is_final_transcript_context,
    projection_was_value_only,
    restore_compacted_climate_source,
)

__all__ = [
    "COMPACTED_CONTRACT_CLIMATE_SOURCE",
    "COMPACTED_FINAL_ROW_CLIMATE_SOURCE",
    "SURVIVAL_TRANSCRIPT_PROJECTION_FORMAT",
    "has_need_values",
    "is_final_transcript_context",
    "persist_survival_evidence_into_transcript_row",
    "persist_survival_evidence_into_transcript_rows",
    "projection_was_value_only",
    "restore_compacted_climate_source",
]
