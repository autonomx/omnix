"""Phase 6.5 - Fallback Scene Builder: Unit tests.

Tests scene shape, grounding, and safety of fallback scene output.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.recovery.fallbacks import FallbackSceneBuilder


def _coherence_summary(location="market"):
    return {
        "scene_summary": {"location": location},
        "active_tensions": [{"text": "bandits nearby"}],
        "unresolved_threads": [{"thread_id": "t1", "title": "Find the artifact"}],
    }


def _anchor(anchor_id="anchor_1", location="tavern"):
    return {"anchor_id": anchor_id, "location": location}


class TestFallbackSceneBuilder:
    def test_build_from_last_good_anchor_returns_grounded_scene(self):
        builder = FallbackSceneBuilder()
        scene = builder.build_from_last_good_anchor(_anchor(), _coherence_summary())
        assert "title" in scene
        assert "body" in scene
        assert "narrative" in scene
        assert scene["metadata"]["recovery"] is True
        assert scene["metadata"]["source"] == "last_good_anchor"
        assert "tavern" in scene["body"]

    def test_build_from_coherence_summary_returns_safe_scene(self):
        builder = FallbackSceneBuilder()
        scene = builder.build_from_coherence_summary(_coherence_summary())
        assert "title" in scene
        assert "body" in scene
        assert scene["metadata"]["recovery"] is True
        assert scene["metadata"]["source"] == "coherence_summary"
        assert "market" in scene["body"]

    def test_build_clarification_scene_returns_question_oriented_output(self):
        builder = FallbackSceneBuilder()
        scene = builder.build_clarification_scene("something unclear", _coherence_summary())
        assert "title" in scene
        assert "body" in scene
        assert scene["metadata"]["recovery"] is True
        assert scene["metadata"]["source"] == "clarification"
        assert "differently" in scene["body"].lower() or "mean" in scene["title"].lower()

    def test_build_contradiction_recovery_scene_uses_contradiction_context(self):
        builder = FallbackSceneBuilder()
        contradictions = [
            {"message": "Guard is alive and dead", "severity": "high"},
            {"message": "Location mismatch", "severity": "medium"},
        ]
        scene = builder.build_contradiction_recovery_scene(contradictions, _coherence_summary())
        assert "title" in scene
        assert "body" in scene
        assert scene["metadata"]["recovery"] is True
        assert scene["metadata"]["source"] == "contradiction_recovery"
        assert scene["metadata"]["contradiction_count"] == 2

    def test_build_director_failure_scene_returns_minimal_valid_output(self):
        builder = FallbackSceneBuilder()
        scene = builder.build_director_failure_scene(_coherence_summary(), reason="Director timed out")
        assert "title" in scene
        assert "body" in scene
        assert "narrative" in scene
        assert scene["metadata"]["recovery"] is True
        assert scene["metadata"]["source"] == "director_failure"

    def test_build_renderer_failure_scene_returns_minimal_valid_output(self):
        builder = FallbackSceneBuilder()
        scene = builder.build_renderer_failure_scene(_coherence_summary())
        assert "title" in scene
        assert "body" in scene
        assert scene["metadata"]["recovery"] is True
        assert scene["metadata"]["source"] == "renderer_failure"

    def test_fallback_scene_does_not_expose_raw_exception_text(self):
        builder = FallbackSceneBuilder()
        # None of the scene builders should include raw exception text
        scenes = [
            builder.build_from_last_good_anchor(_anchor(), _coherence_summary()),
            builder.build_from_coherence_summary(_coherence_summary()),
            builder.build_clarification_scene("test", _coherence_summary()),
            builder.build_director_failure_scene(_coherence_summary(), reason="err"),
            builder.build_renderer_failure_scene(_coherence_summary()),
        ]
        for scene in scenes:
            assert "Traceback" not in scene.get("body", "")
            assert "Exception" not in scene.get("body", "")
            assert "Error" not in scene.get("body", "")
            assert "Traceback" not in scene.get("title", "")
