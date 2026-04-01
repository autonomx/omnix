import heapq


def distance(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def is_near(a, b, radius=5):
    return distance(a, b) <= radius


def heuristic(a, b):
    """Manhattan distance heuristic for A* pathfinding."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors(pos, world):
    """Get valid neighboring positions with 8-directional movement."""
    x, y = pos
    max_x, max_y = world.size

    candidates = [
        (x+1, y), (x-1, y), (x, y+1), (x, y-1),
        (x+1, y+1), (x-1, y-1), (x+1, y-1), (x-1, y+1)
    ]

    return [
        p for p in candidates
        if 0 <= p[0] < max_x and 0 <= p[1] < max_y
    ]


def build_occupancy(session):
    """Build occupancy map from active NPCs."""
    return {npc.position for npc in session.npcs if npc.is_active}


def astar(start, goal, session):
    """A* pathfinding with obstacle avoidance using occupancy map."""
    world = session.world
    occupied = build_occupancy(session)

    open_set = []
    heapq.heappush(open_set, (0, start))

    came_from = {}
    g_score = {start: 0}

    while open_set:
        _, current = heapq.heappop(open_set)

        if current == goal:
            return reconstruct_path(came_from, current)

        for n in neighbors(current, world):
            # Skip occupied cells unless it's the goal
            if n in occupied and n != goal:
                continue

            tentative = g_score[current] + 1

            if tentative < g_score.get(n, float("inf")):
                came_from[n] = current
                g_score[n] = tentative
                f = tentative + heuristic(n, goal)
                heapq.heappush(open_set, (f, n))

    return []


def reconstruct_path(came_from, current):
    """Reconstruct path from came_from map."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return list(reversed(path))