from __future__ import annotations

from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from .gapper_dataset import GapperUniverseSnapshot


_ET = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
FINVIZ_ATOMIC_FIRST_PAGE_MAX = 20
FINVIZ_ATOMIC_FIRST_PAGE_TAG = "omnix-atomic-first-page-v1"


class UniverseIntegrityAssessment(BaseModel):
    """Derived prospective-integrity state for one frozen strategy universe."""

    model_config = ConfigDict(frozen=True)

    capture_on_time: bool
    cohort_complete: bool
    cohort_integrity: Literal["valid", "invalid"]
    market_data_complete: bool
    prospective_eligible: bool
    reason_codes: tuple[str, ...] = ()


def finviz_atomic_source_locator(source_url: str) -> str:
    clean = str(source_url or "").split("#", 1)[0]
    return f"{clean}#{FINVIZ_ATOMIC_FIRST_PAGE_TAG}"


def assess_universe_integrity(snapshot: GapperUniverseSnapshot) -> UniverseIntegrityAssessment:
    """Derive fail-closed prospective validity without mutating the frozen snapshot.

    Old Finviz archives created by the former multi-request pagination path do
    not carry the atomic-first-page provenance tag and therefore cannot silently
    become prospective evidence after this hardening change.
    """

    reasons: list[str] = []
    evaluation_et = snapshot.evaluation_time.astimezone(_ET)
    is_finviz = snapshot.discovery_source == "finviz"

    capture_on_time = True
    cohort_complete = True
    cohort_integrity: Literal["valid", "invalid"] = "valid"

    if is_finviz:
        capture_on_time = (
            evaluation_et.date() == snapshot.session_date
            and evaluation_et.time() < _REGULAR_OPEN
        )
        if not capture_on_time:
            reasons.append("FINVIZ_CAPTURE_NOT_PREOPEN")

        locator = str(snapshot.source_locator or "")
        atomic = f"#{FINVIZ_ATOMIC_FIRST_PAGE_TAG}" in locator
        cohort_size = len(snapshot.source_candidate_symbols)
        cohort_complete = (
            atomic
            and 0 < cohort_size <= FINVIZ_ATOMIC_FIRST_PAGE_MAX
        )
        if not cohort_complete:
            reasons.append("FINVIZ_ATOMIC_COHORT_UNPROVEN")
        cohort_integrity = "valid" if cohort_complete else "invalid"

    market_data_complete = all(
        candidate.market_data_complete for candidate in snapshot.candidates
    )
    if snapshot.candidates and not market_data_complete:
        reasons.append("CANDIDATE_MARKET_DATA_INCOMPLETE")

    prospective_eligible = (
        capture_on_time
        and cohort_complete
        and cohort_integrity == "valid"
    )
    return UniverseIntegrityAssessment(
        capture_on_time=capture_on_time,
        cohort_complete=cohort_complete,
        cohort_integrity=cohort_integrity,
        market_data_complete=market_data_complete,
        prospective_eligible=prospective_eligible,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "FINVIZ_ATOMIC_FIRST_PAGE_MAX",
    "FINVIZ_ATOMIC_FIRST_PAGE_TAG",
    "UniverseIntegrityAssessment",
    "assess_universe_integrity",
    "finviz_atomic_source_locator",
]
