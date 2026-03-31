class Action:
    def __init__(self, name, preconditions, effects, cost=1):
        self.name = name
        self.preconditions = preconditions
        self.effects = effects
        self.cost = cost

    def is_valid(self, state):
        return all(state.get(k) == v for k, v in self.preconditions.items())

    def apply(self, state):
        new_state = state.copy()
        new_state.update(self.effects)
        return new_state


class GOAPPlanner:
    def plan(self, start_state, goal, actions):
        open_list = [(start_state, [], 0)]

        while open_list:
            state, path, cost = open_list.pop(0)

            if all(state.get(k) == v for k, v in goal.items()):
                return path

            for action in actions:
                if action.is_valid(state):
                    new_state = action.apply(state)
                    open_list.append((
                        new_state,
                        path + [action],
                        cost + action.cost
                    ))

        return []