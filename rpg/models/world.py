class Faction:
    def __init__(self, name: str):
        self.name = name
        self.relations = {}

class Territory:
    def __init__(self, name: str, owner: str):
        self.name = name
        self.owner = owner

def resolve_territory_control(territory: Territory, attackers):
    if len(attackers) > 2:
        territory.owner = attackers[0].faction