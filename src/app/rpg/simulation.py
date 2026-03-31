def process(session, intent):
    events = []

    source = intent.get("source", "player")

    if intent["action"] == "attack":
        target = find_target(session, intent.get("target"))

        if not target:
            return {"success": False, "events": []}

        damage = 10
        target.hp -= damage

        events.append({
            "type": "damage",
            "source": source,
            "target": target.id,
            "amount": damage
        })

        if target.hp <= 0:
            target.is_active = False
            events.append({
                "type": "death",
                "target": target.id
            })

    return {
        "success": True,
        "events": events
    }


def apply_events(session, events):
    for event in events:
        if event["type"] == "death":
            npc = find_npc(session, event["target"])
            if npc:
                npc.is_active = False


def find_target(session, target_id):
    for npc in session.npcs:
        if npc.id == target_id:
            return npc
    return None


def find_npc(session, npc_id):
    return find_target(session, npc_id)