from heapq import heappush, heappop


class Node:
    def __init__(self, state, cost, plan):
        self.state = state
        self.cost = cost
        self.plan = plan

    def __lt__(self, other):
        return self.cost < other.cost


def goal_satisfied(state, goal):
    for k, v in goal.items():
        if state.get(k) != v:
            return False
    return True


def plan(initial_state, goal, actions, max_depth=5):
    open_list = []
    heappush(open_list, Node(initial_state, 0, []))

    while open_list:
        node = heappop(open_list)

        if goal_satisfied(node.state, goal):
            return node.plan

        if len(node.plan) >= max_depth:
            continue

        for action in actions:
            if action.is_applicable(node.state):
                new_state = action.apply(node.state)
                new_plan = node.plan + [action]
                new_cost = node.cost + action.cost
                heappush(open_list, Node(new_state, new_cost, new_plan))

    return []