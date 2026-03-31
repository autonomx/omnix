from rpg.simulation import find_npc


def handle_damage(event, session):
    target = find_npc(session, event["target"])
    if not target:
        return

    target.hp -= event["amount"]

    if target.hp <= 0:
        session.event_bus.emit({
            "type": "death",
            "target": target.id
        })


def handle_death(event, session):
    npc = find_npc(session, event["target"])
    if npc:
        npc.is_active = False


def register(bus, session):
    bus.subscribe("damage", lambda e: handle_damage(e, session))
    bus.subscribe("death", lambda e: handle_death(e, session))