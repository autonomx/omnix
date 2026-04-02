import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app", "rpg", "ai", "emergence"))
from emergence_tracker import EmergenceTracker
from divergence_analyzer import DivergenceAnalyzer
from causality_tracker import CausalityTracker
from loop_detector import LoopDetector
from emergence_metrics import EmergenceMetrics

class TestEmergenceRegression:
    def test_tracker_handles_many_actions(self):
        tracker = EmergenceTracker()
        for i in range(1000):
            tracker.record_action(i, f"npc{i%10}", {"type": "action"})
        assert tracker.get_total_actions() == 1000
    def test_divergence_handles_many_npcs(self):
        tracker = EmergenceTracker()
        for i in range(100):
            tracker.record_action(i, f"npc{i}", {"type": f"action{i}"})
        analyzer = DivergenceAnalyzer()
        npc_ids = [f"npc{i}" for i in range(100)]
        divergence = analyzer.measure_divergence(tracker, npc_ids)
        assert divergence == 1.0
    def test_causality_score_caps(self):
        tracker = CausalityTracker()
        for i in range(100):
            tracker.link({"type": f"a{i}"}, {"change": f"e{i}"})
        assert tracker.causality_score() == 1.0
    def test_loop_detector_handles_long_sequences(self):
        detector = LoopDetector()
        seq = ["a","b","c"] * 100
        assert detector.detect(seq) is True
    def test_metrics_clamped(self):
        metrics = EmergenceMetrics()
        for _ in range(100):
            score = metrics.compute(0.0, 0.0, 1.0)
            assert 0.0 <= score <= 1.0
