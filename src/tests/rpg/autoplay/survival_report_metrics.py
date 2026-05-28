"""Autoplay-facing survival report metric helpers.

Bundle BG keeps the aggregation implementation in ``app.rpg`` so runtime/report
exports can share it, while exposing this thin test-harness import path for the
autoplay campaign report pipeline.
"""
from __future__ import annotations

from app.rpg.survival_report_metrics import (  # noqa: F401
    build_survival_report_metrics,
    merge_survival_report_metrics,
    render_survival_report_html,
)

__all__ = [
    "build_survival_report_metrics",
    "merge_survival_report_metrics",
    "render_survival_report_html",
]
