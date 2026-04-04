"""Phase 7.8 — Arc Control Presenters.

UI-safe presentation of arc control state.  All output shapes are
stable dicts suitable for frontend consumption.
"""

from __future__ import annotations

from typing import Any


class ArcControlPresenter:
    """Present arc-control state in stable, UI-safe shapes."""

    def present_arc_panel(self, controller: Any) -> dict:
        """Return a stable dict for the arc panel.

        Shape::

            {
                "title": "Arcs",
                "items": [ <arc_dict>, ... ],
                "count": <int>,
            }
        """
        items = [a.to_dict() for a in controller.arcs.values()]
        return {
            "title": "Arcs",
            "items": items,
            "count": len(items),
        }

    def present_reveal_panel(self, controller: Any) -> dict:
        """Return a stable dict for the reveal panel.

        Shape::

            {
                "title": "Reveals",
                "items": [ <reveal_dict>, ... ],
                "count": <int>,
            }
        """
        items = [r.to_dict() for r in controller.reveals.values()]
        return {
            "title": "Reveals",
            "items": items,
            "count": len(items),
        }

    def present_pacing_plan_panel(self, controller: Any) -> dict:
        """Return a stable dict for the pacing-plan panel.

        Shape::

            {
                "title": "Pacing Plan",
                "items": [ <plan_dict>, ... ],
                "count": <int>,
            }
        """
        items = [p.to_dict() for p in controller.pacing_plans.values()]
        return {
            "title": "Pacing Plan",
            "items": items,
            "count": len(items),
        }

    def present_scene_bias_panel(self, controller: Any) -> dict:
        """Return a stable dict for the scene-bias panel.

        Shape::

            {
                "title": "Scene Bias",
                "items": [ <bias_dict>, ... ],
                "count": <int>,
            }
        """
        items = [b.to_dict() for b in controller.scene_biases.values()]
        return {
            "title": "Scene Bias",
            "items": items,
            "count": len(items),
        }

    def present_director_context(self, context: dict) -> dict:
        """Return a stable dict for the director context.

        The input *context* is the output of
        ``ArcControlController.build_director_context()``.

        Shape::

            {
                "title": "Director Context",
                "active_arcs": [...],
                "due_reveals": [...],
                "active_pacing_plan": {...} | None,
                "active_scene_bias": {...} | None,
            }
        """
        return {
            "title": "Director Context",
            "active_arcs": context.get("active_arcs", []),
            "due_reveals": context.get("due_reveals", []),
            "active_pacing_plan": context.get("active_pacing_plan"),
            "active_scene_bias": context.get("active_scene_bias"),
        }
