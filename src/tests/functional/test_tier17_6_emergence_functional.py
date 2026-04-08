import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app", "rpg", "ai", "emergence"))
from causality_tracker import CausalityTracker
from divergence_analyzer import DivergenceAnalyzer
from emergence_metrics import EmergenceMetrics
from emergence_tracker import EmergenceTracker
from loop_detector import LoopDetector


class TestEmergenceFunctional:
    def test_full_emergence_pipeline(self):
        tracker = EmergenceTracker()
        tracker.record_action(1, "npc1", {"type": "attack"})
        tracker.record_action(2, "npc2", {"type": "assist"})
        tracker.record_world_change(1, "tension", 0.1)
        assert tracker.get_total_actions() == 2
        assert tracker.get_total_world_changes() == 1
    def test_divergence_analysis(self):
        tracker = EmergenceTracker()
        tracker.record_action(1, "npc1", {"type": "attack"})
        tracker.record_action(2, "npc2", {"type": "assist"})
        analyzer = DivergenceAnalyzer()
        divergence = analyzer.measure_divergence(tracker, ["npc1", "npc2"])
        assert divergence == 1.0
    def test_causality_tracking(self):
        tracker = CausalityTracker()
        tracker.link({"type": "attack"}, {"change": "tension"})
        assert len(tracker.get_links()) == 1
        assert tracker.causality_score() == 0.1
    def test_loop_detection(self):
        detector = LoopDetector()
        assert detector.detect(["a","b","c","a","b","c"]) is True
        assert detector.detect(["a","b","c","x","y","z"]) is False
    def test_emergence_metrics(self):
        metrics = EmergenceMetrics()
        score = metrics.compute(1.0, 1.0, 0.0)
        assert score == 0.9
