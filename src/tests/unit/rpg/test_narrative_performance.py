"""Performance Benchmarks — Narrative Layer Performance Testing.

This module provides benchmarks for measuring the narrative system's
tick throughput with various configurations and event counts.

Purpose:
    Identify performance bottlenecks in event scoring, focus selection,
    and narrative generation under realistic loads.

Usage:
    pytest src/tests/unit/rpg/test_narrative_performance.py -v
    pytest src/tests/unit/rpg/test_narrative_performance.py -v --benchmark-only

Benchmarks:
    - Event conversion throughput (10, 100, 1000 events)
    - Focus selection performance (various event counts)
    - Scene update latency
    - Template generation speed
    - End-to-end player loop timing

Environment Variables:
    BENCH_ITERATIONS: Override iteration count (default: 5000 for conversion)
    BENCH_TIMEOUT: Override timeout in seconds (default: 60)
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import pytest

# Import narrative components
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.narrative.narrative_event import NarrativeEvent
from rpg.narrative.narrative_director import NarrativeDirector
from rpg.narrative.scene_manager import SceneManager
from rpg.narrative.narrative_generator import NarrativeGenerator
from rpg.core.player_loop import PlayerLoop


# Configuration from environment
ITERATIONS = int(os.environ.get("BENCH_ITERATIONS", "5000"))
TIMEOUT = float(os.environ.get("BENCH_TIMEOUT", "60"))


def generate_test_events(count: int) -> List[Dict[str, Any]]:
    """Generate test events for benchmarking.
    
    Args:
        count: Number of events to generate.
    
    Returns:
        List of test event dicts.
    """
    event_types = [
        "combat", "death", "damage", "heal", "speak",
        "move", "critical_hit", "flee", "story_event",
    ]
    locations = [
        "town_square", "forest", "dungeon", "castle",
        "tavern", "market", "ruins", "bridge",
    ]
    
    events = []
    for i in range(count):
        events.append({
            "type": event_types[i % len(event_types)],
            "description": f"Event {i}: {event_types[i % len(event_types)]}",
            "actors": [f"actor_{i % 10}", f"actor_{(i + 1) % 10}"],
            "location": locations[i % len(locations)],
            "tick": i,
        })
    return events


def elapsed_ms(start: float, end: float) -> float:
    """Calculate elapsed time in milliseconds.
    
    Args:
        start: Start time from time.perf_counter().
        end: End time from time.perf_counter().
    
    Returns:
        Elapsed time in milliseconds.
    """
    return (end - start) * 1000


def events_per_second(count: int, seconds: float) -> float:
    """Calculate events per second throughput.
    
    Args:
        count: Number of events processed.
        seconds: Total time in seconds.
    
    Returns:
        Throughput in events per second.
    """
    if seconds <= 0:
        return float("inf")
    return count / seconds


class TestEventConversionBenchmark:
    """Benchmarks for NarrativeDirector event conversion."""
    
    def test_convert_10_events(self):
        """Measure event conversion for 10 events."""
        director = NarrativeDirector()
        events = generate_test_events(10)
        
        start = time.perf_counter()
        for _ in range(100):
            result = director.convert_events(events)
            director.clear_buffer()
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        eps = events_per_second(10 * 100, end - start)
        print(f"\n10 events: {ms:.2f}ms total, {eps:,.0f} events/sec")
        assert ms < 100, f"Conversion too slow: {ms:.2f}ms"
    
    def test_convert_100_events(self):
        """Measure event conversion for 100 events."""
        director = NarrativeDirector()
        events = generate_test_events(100)
        
        start = time.perf_counter()
        result = director.convert_events(events)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        eps = events_per_second(100, end - start)
        print(f"\n100 events: {ms:.2f}ms total, {eps:,.0f} events/sec")
        assert ms < 50, f"Conversion too slow: {ms:.2f}ms"
    
    def test_convert_1000_events(self):
        """Measure event conversion for 1000 events."""
        director = NarrativeDirector()
        events = generate_test_events(1000)
        
        start = time.perf_counter()
        result = director.convert_events(events)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        eps = events_per_second(1000, end - start)
        print(f"\n1000 events: {ms:.2f}ms total, {eps:,.0f} events/sec")
        assert ms < 200, f"Conversion too slow: {ms:.2f}ms"
    
    def test_convert_10000_events(self):
        """Measure event conversion for 10000 events."""
        director = NarrativeDirector()
        events = generate_test_events(10000)
        
        start = time.perf_counter()
        result = director.convert_events(events)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        assert ms < 2000, f"Conversion too slow: {ms:.2f}ms"


class TestFocusSelectionBenchmark:
    """Benchmarks for focus event selection."""
    
    def test_select_focus_10_events(self, benchmark):
        """Measure focus selection for 10 events."""
        director = NarrativeDirector()
        events = [
            NarrativeEvent(
                id=str(i),
                type="combat",
                description=f"Event {i}",
                actors=["player"],
                importance=0.5,
                emotional_weight=0.3,
            )
            for i in range(10)
        ]
        
        start = time.perf_counter()
        for _ in range(1000):
            result = director.select_focus_events(events, max_events=5)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        print(f"\nFocus select x1000: {ms:.2f}ms")
        assert ms < 100, f"Selection too slow: {ms:.2f}ms"
    
    def test_select_focus_1000_events(self):
        """Measure focus selection for 1000 events."""
        director = NarrativeDirector()
        events = [
            NarrativeEvent(
                id=str(i),
                type="combat",
                description=f"Event {i}",
                actors=["player"],
                importance=0.5,
                emotional_weight=0.3,
            )
            for i in range(1000)
        ]
        
        start = time.perf_counter()
        result = director.select_focus_events(events, max_events=5)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        print(f"\n1000 -> 5 focus: {ms:.2f}ms")
        assert ms < 10, f"Selection too slow: {ms:.2f}ms"


class TestSceneManagerBenchmark:
    """Benchmarks for scene management."""
    
    def test_scene_update_many_events(self):
        """Measure scene update with many events."""
        sm = SceneManager()
        events = generate_test_events(50)
        
        start = time.perf_counter()
        for i in range(100):
            sm.update_scene([{
                "type": "combat",
                "description": f"Combat event {i}",
                "actors": ["player", f"enemy_{i % 5}"],
                "location": f"location_{i % 3}",
            }])
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        eps = events_per_second(100, end - start)
        print(f"\n100 scene updates: {ms:.2f}ms, {eps:,.0f} updates/sec")
        assert ms < 50, f"Updates too slow: {ms:.2f}ms"
    
    def test_scene_transition_latency(self):
        """Measure scene transition latency."""
        sm = SceneManager()
        
        start = time.perf_counter()
        for i in range(20):
            sm.update_scene([{
                "type": "move",
                "description": f"Moving to location {i}",
                "actors": ["player"],
                "location": f"location_{i}",
            }])
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        per_transition = ms / 20
        print(f"\n20 transitions: {ms:.2f}ms ({per_transition:.3f}ms each)")
        assert ms < 20, f"Transitions too slow: {ms:.2f}ms"


class TestNarrativeGeneratorBenchmark:
    """Benchmarks for narrative generation."""
    
    def test_template_generation_speed(self):
        """Measure template generation speed."""
        gen = NarrativeGenerator()  # Template mode
        events = [
            NarrativeEvent(
                id=str(i),
                type="combat",
                description=f"Combat {i}",
                actors=["hero", f"monster_{i}"],
            )
            for i in range(10)
        ]
        ctx = {"location": "arena", "participants": ["hero"], "mood": "tense"}
        
        start = time.perf_counter()
        for _ in range(100):
            result = gen.generate(events, ctx)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        per_gen = ms / 100
        print(f"\n100 template generations: {ms:.2f}ms ({per_gen:.2f}ms each)")
        assert ms < 500, f"Template generation too slow: {ms:.2f}ms"
    
    def test_large_event_narration(self):
        """Measure narration for large event sets."""
        gen = NarrativeGenerator()
        events = [
            NarrativeEvent(
                id=str(i),
                type="combat",
                description=f"Battle {i}: The hero faces enemy {i}",
                actors=["hero", f"enemy_{i}"],
            )
            for i in range(50)
        ]
        ctx = {"location": "battlefield", "participants": ["hero"], "mood": "dark"}
        
        start = time.perf_counter()
        result = gen.generate(events, ctx)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        word_count = len(result.split()) if result else 0
        print(f"\n50 events narration: {ms:.2f}ms, {word_count} words")
        assert ms < 50, f"Large narration too slow: {ms:.2f}ms"


class TestEndToEndBenchmark:
    """End-to-end player loop benchmarks."""
    
    def test_player_loop_throughput(self):
        """Measure end-to-end player loop throughput."""
        def simulate_fn():
            return generate_test_events(5)
        
        director = NarrativeDirector()
        sm = SceneManager()
        gen = NarrativeGenerator()
        loop = PlayerLoop(
            director=director,
            scene_manager=sm,
            narrator=gen,
            simulate_fn=simulate_fn,
        )
        
        start = time.perf_counter()
        for i in range(100):
            result = loop.step(f"Action {i}")
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        steps_per_sec = 100 / (end - start) if (end - start) > 0 else float("inf")
        print(f"\n100 loop steps: {ms:.2f}ms ({steps_per_sec:,.0f} steps/sec)")
        assert ms < 500, f"Loop too slow: {ms:.2f}ms"
    
    def test_rapid_consecutive_inputs(self):
        """Measure performance with rapid player inputs."""
        def simulate_fn():
            return [
                {"type": "combat", "description": "Player attacks", "actors": ["player", "enemy"]},
            ]
        
        director = NarrativeDirector()
        sm = SceneManager()
        gen = NarrativeGenerator()
        loop = PlayerLoop(
            director=director,
            scene_manager=sm,
            narrator=gen,
            simulate_fn=simulate_fn,
        )
        
        inputs = ["I attack", "I defend", "I flee", "I speak", "I wait"] * 20
        
        start = time.perf_counter()
        for inp in inputs:
            result = loop.step(inp)
        end = time.perf_counter()
        
        ms = elapsed_ms(start, end)
        steps_per_sec = 100 / (end - start) if (end - start) > 0 else float("inf")
        print(f"\n100 rapid inputs: {ms:.2f}ms ({steps_per_sec:,.0f} steps/sec)")
        assert ms < 500, f"Rapid inputs too slow: {ms:.2f}ms"


class TestMemoryBenchmark:
    """Memory usage benchmarks."""
    
    def test_event_buffer_memory(self):
        """Test that event buffers stay bounded."""
        director = NarrativeDirector(max_buffer=10)
        
        # Process more events than buffer can hold
        for i in range(100):
            events = [{"type": "combat", "description": f"Event {i}"}]
            director.convert_events(events)
        
        assert len(director.recent_events) <= 10
    
    def test_scene_memory_bounded(self):
        """Test that scene memory stays bounded."""
        sm = SceneManager(max_events_per_scene=5, max_completed_scenes=3)
        
        # Create many scene updates
        for i in range(50):
            sm.update_scene([{
                "type": "move",
                "description": f"Move {i}",
                "actors": ["player"],
                "location": f"loc_{i}",
            }])
        
        if sm.active_scene:
            assert len(sm.active_scene.recent_events) <= 5
        assert len(sm.scenes_completed) <= 3