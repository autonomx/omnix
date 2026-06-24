# Phase 36 — Environmental Scene Trace Runtime

Phase 36 wires prior scene state into sequential report/autoplay rows.

Implemented:

- a compact scene trace helper that carries the previous row's environmental snapshot;
- report-surface integration before environmental sections are built;
- weather/change return-visit detection without caller-provided previous_scene;
- summary-level carried-row counts;
- regression coverage for direct carry, report-surface carry, and summary aggregation.

Verification remains gated by GitHub Actions on the implementation PR.
