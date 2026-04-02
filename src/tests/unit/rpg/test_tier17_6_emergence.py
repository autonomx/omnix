import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app", "rpg", "ai", "emergence"))
from emergence_tracker import EmergenceTracker
from divergence_analyzer import DivergenceAnalyzer
from causality_tracker import CausalityTracker
from loop_detector import LoopDetector
from emergence_metrics import EmergenceMetrics

class TestEmergenceTracker:
    def test_record_action(self):
        t = EmergenceTracker()
        t.record_action(1, "npc1", {"type": "attack"})
        assert t.get_total_actions() == 1
        assert t.get_actions_for_npc("npc1")[0]["action"] == "attack"
    def test_record_world_change(self):
        t = EmergenceTracker()
        t.record_world_change(1, "tension", 0.1)
        assert t.get_total_world_changes() == 1
    def test_get_actions_for_npc(self):
        t = EmergenceTracker()
        t.record_action(1, "npc1", {"type": "attack"})
        t.record_action(2, "npc2", {"type": "assist"})
        assert len(t.get_actions_for_npc("npc1")) == 1
    def test_reset(self):
        t = EmergenceTracker()
        t.record_action(1, "npc1", {"type": "attack"})
        t.reset()
        assert t.get_total_actions() == 0

class TestDivergenceAnalyzer:
    def test_measure_divergence_different(self):
        t = EmergenceTracker()
        t.record_action(1, "npc1", {"type": "attack"})
        t.record_action(2, "npc2", {"type": "assist"})
        d = DivergenceAnalyzer()
        assert d.measure_divergence(t, ["npc1", "npc2"]) == 1.0
    def test_measure_divergence_same(self):
        t = EmergenceTracker()
        t.record_action(1, "npc1", {"type": "attack"})
        t.record_action(2, "npc2", {"type": "attack"})
        d = DivergenceAnalyzer()
        assert d.measure_divergence(t, ["npc1", "npc2"]) == 0.5
    def test_divergence_empty(self):
        t = EmergenceTracker()
        d = DivergenceAnalyzer()
        assert d.measure_divergence(t, ["npc1"]) == 0.0

class TestCausalityTracker:
    def test_link(self):
        c = CausalityTracker()
        c.link({"type": "attack"}, {"change": "tension"})
        assert len(c.get_links()) == 1
    def test_causality_score(self):
        c = CausalityTracker()
        assert c.causality_score() == 0.0
        for i in range(5):
            c.link({"type": "a"}, {"change": "e"})
        assert c.causality_score() == 0.5
    def test_causality_max(self):
        c = CausalityTracker()
        for i in range(20):
            c.link({"type": "a"}, {"change": "e"})
        assert c.causality_score() == 1.0

class TestLoopDetector:
    def test_detect_loop(self):
        d = LoopDetector()
        assert d.detect(["a","b","c","a","b","c"]) is True
    def test_no_loop(self):
        d = LoopDetector()
        assert d.detect(["a","b","c","x","y","z"]) is False
    def test_too_short(self):
        d = LoopDetector()
        assert d.detect(["a","b"]) is False

class TestEmergenceMetrics:
    def test_compute_default(self):
        m = EmergenceMetrics()
        assert m.compute(1.0, 1.0, 0.0) == 0.9
    def test_compute_penalty(self):
        m = EmergenceMetrics()
        assert abs(m.compute(0.5, 0.5, 1.0) - 0.15) < 0.001
    def test_compute_clamped(self):
        m = EmergenceMetrics()
        score = m.compute(0.0, 0.0, 1.0)
        assert 0.0 <= score <= 1.0
