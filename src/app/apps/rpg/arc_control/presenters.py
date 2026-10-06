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
        items = sorted(
            [a.to_dict() for a in controller.arcs.values()],
            key=lambda x: x.get("arc_id", ""),
        )
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
        items = sorted(
            [r.to_dict() for r in controller.reveals.values()],
            key=lambda x: x.get("reveal_id", ""),
        )
        return {
            "title": "Reveals",
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
        items = sorted(
            [b.to_dict() for b in controller.scene_biases.values()],
            key=lambda x: x.get("bias_id", ""),
        )
        return {
            "title": "Scene Bias",
            "items": items,
            "count": len(items),
        }

