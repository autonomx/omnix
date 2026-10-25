"""Phase 4.5 — Player Action → Simulation Feedback.

Provides deterministic action → consequence mapping so that player input
feeds into the existing effects/incident pipeline instead of bypassing it.

Design principles:
- Player actions produce **consequences**, not direct pressure mutations.
  The effects system applies those consequences on the next tick.
- Faction escalation is scoped to *related* factions (those connected
  to the target thread), not all factions globally.
- Every action carries a stable action_id so duplicate submissions are
  silently ignored (idempotency protection).

The gameplay loop enabled by this module is:

    Scene → Player Action → Consequences → Effects → New World State → New Scenes

All mutations are fully deterministic given the same (state, action) pair.
"""

from __future__ import annotations


# Phase 8: player-facing action summaries

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------

INTERVENE_THREAD = "intervene_thread"
SUPPORT_FACTION = "support_faction"
ESCALATE_CONFLICT = "escalate_conflict"


# ---------------------------------------------------------------------------
# Core: action → consequences (NOT direct mutations)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Status helpers (mirror world_simulation for consistency)
# ---------------------------------------------------------------------------
