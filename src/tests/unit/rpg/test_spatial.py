"""Unit tests for RPG spatial utilities."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app'))

from rpg.spatial import (
    astar,
    build_occupancy,
    distance,
    euclidean_distance,
    heuristic,
    in_range,
    is_near,
    neighbors,
    reconstruct_path,
)


class TestDistance:
    """Test distance functions."""

    def test_manhattan_distance_same_point(self):
        assert distance((0, 0), (0, 0)) == 0

    def test_manhattan_distance_horizontal(self):
        assert distance((0, 0), (5, 0)) == 5

    def test_manhattan_distance_vertical(self):
        assert distance((0, 0), (0, 3)) == 3

    def test_manhattan_distance_diagonal(self):
        assert distance((0, 0), (3, 4)) == 7

    def test_euclidean_distance_same_point(self):
        assert euclidean_distance((0, 0), (0, 0)) == 0

    def test_euclidean_distance_horizontal(self):
        assert euclidean_distance((0, 0), (3, 0)) == 3

    def test_euclidean_distance_3_4_5(self):
        assert euclidean_distance((0, 0), (3, 4)) == 5

    def test_euclidean_distance_diagonal(self):
        assert abs(euclidean_distance((0, 0), (1, 1)) - math.sqrt(2)) < 0.001


class TestInRange:
    """Test in_range function."""

    def test_in_range_within(self):
        assert in_range((0, 0), (3, 4), 5) is True

    def test_in_range_exact(self):
        assert in_range((0, 0), (3, 0), 3) is True

    def test_in_range_outside(self):
        assert in_range((0, 0), (10, 0), 5) is False

    def test_in_range_same_point(self):
        assert in_range((0, 0), (0, 0), 1) is True


class TestIsNear:
    """Test is_near function."""

    def test_is_near_within_default_radius(self):
        # distance((0,0),(3,4)) = 7, default radius = 5, so 7 > 5 = False
        assert is_near((0, 0), (3, 4)) is False

    def test_is_near_within_custom_radius(self):
        assert is_near((0, 0), (3, 4), radius=10) is True

    def test_is_near_outside_radius(self):
        assert is_near((0, 0), (10, 10), radius=5) is False

    def test_is_near_same_point(self):
        assert is_near((0, 0), (0, 0)) is True

    def test_is_near_within_radius_7(self):
        assert is_near((0, 0), (3, 4), radius=7) is True


class TestHeuristic:
    """Test heuristic function."""

    def test_heuristic_same_point(self):
        assert heuristic((0, 0), (0, 0)) == 0

    def test_heuristic_horizontal(self):
        assert heuristic((0, 0), (5, 0)) == 5

    def test_heuristic_diagonal(self):
        assert heuristic((0, 0), (3, 4)) == 7


class TestNeighbors:
    """Test neighbors function."""

    def test_neighbors_center(self):
        world = type('World', (), {'size': (10, 10)})()
        n = neighbors((5, 5), world)
        assert len(n) == 8  # 8-directional

    def test_neighbors_corner(self):
        world = type('World', (), {'size': (10, 10)})()
        n = neighbors((0, 0), world)
        assert len(n) == 3  # Only 3 valid neighbors at corner

    def test_neighbors_edge(self):
        world = type('World', (), {'size': (10, 10)})()
        n = neighbors((0, 5), world)
        assert len(n) == 5  # 5 valid neighbors at edge

    def test_neighbors_all_within_bounds(self):
        world = type('World', (), {'size': (10, 10)})()
        n = neighbors((5, 5), world)
        for pos in n:
            assert 0 <= pos[0] < 10
            assert 0 <= pos[1] < 10


class TestAStar:
    """Test A* pathfinding."""

    def test_astar_same_position(self):
        session = type('Session', (), {
            'world': type('World', (), {'size': (10, 10)})(),
            'npcs': []
        })()
        path = astar((5, 5), (5, 5), session)
        assert path == [(5, 5)]

    def test_astar_adjacent(self):
        session = type('Session', (), {
            'world': type('World', (), {'size': (10, 10)})(),
            'npcs': []
        })()
        path = astar((0, 0), (0, 1), session)
        assert len(path) == 2
        assert path[0] == (0, 0)
        assert path[1] == (0, 1)

    def test_astar_straight_line(self):
        session = type('Session', (), {
            'world': type('World', (), {'size': (10, 10)})(),
            'npcs': []
        })()
        path = astar((0, 0), (0, 5), session)
        assert path[0] == (0, 0)
        assert path[-1] == (0, 5)

    def test_astar_with_obstacle(self):
        npc = type('NPC', (), {'position': (1, 0), 'is_active': True})()
        session = type('Session', (), {
            'world': type('World', (), {'size': (10, 10)})(),
            'npcs': [npc]
        })()
        path = astar((0, 0), (2, 0), session)
        assert path[0] == (0, 0)
        assert path[-1] == (2, 0)
        # Path should go around obstacle
        assert (1, 0) not in path[:-1]  # Goal can be occupied

    def test_astar_no_path(self):
        # Block all paths
        npcs = [
            type('NPC', (), {'position': (0, 1), 'is_active': True})(),
            type('NPC', (), {'position': (1, 0), 'is_active': True})(),
            type('NPC', (), {'position': (1, 1), 'is_active': True})(),
        ]
        session = type('Session', (), {
            'world': type('World', (), {'size': (10, 10)})(),
            'npcs': npcs
        })()
        path = astar((0, 0), (2, 2), session)
        assert path == []


class TestReconstructPath:
    """Test path reconstruction."""

    def test_reconstruct_path_single(self):
        came_from = {}
        path = reconstruct_path(came_from, (0, 0))
        assert path == [(0, 0)]

    def test_reconstruct_path_linear(self):
        came_from = {
            (0, 1): (0, 0),
            (0, 2): (0, 1),
        }
        path = reconstruct_path(came_from, (0, 2))
        assert path == [(0, 0), (0, 1), (0, 2)]