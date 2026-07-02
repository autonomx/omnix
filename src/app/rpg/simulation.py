def _intent_action(intent):
    action = str(intent.get("action") or "").strip().lower()
    if action:
        return action

    raw_intent = str(intent.get("intent") or intent.get("command") or "").strip().lower()
    if any(word in raw_intent for word in ("attack", "fight", "strike", "hit")):
        return "attack"
    if any(word in raw_intent for word in ("look", "observe", "inspect", "wait", "rest", "inventory")):
        return "observe"
    return "noop"


def process(session, intent):
    events = []

    source = intent.get("source", "player")
    action = _intent_action(intent)

    if action == "attack":
        target = find_target(session, intent.get("target"))

        if not target:
            return {"success": False, "events": []}

        damage = 10

        events.append({
            "type": "damage",
            "source": source,
            "target": target.id,
            "amount": damage
        })

        # DO NOT check death here — handled in combat_system

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
