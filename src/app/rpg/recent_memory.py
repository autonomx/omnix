VERSION = "recent_memory_v1"

def _dict(value):
    return value if isinstance(value, dict) else {}

def _list(value):
    return value if isinstance(value, list) else []

def recent_memory(session):
    runtime = _dict(_dict(session).get("runtime_state"))
    memory = _dict(runtime.get("recent_memory"))
    turns = _list(memory.get("turns"))[-12:]
    dialogue = _list(memory.get("dialogue"))[-20:]
    return {"version": VERSION, "turns": turns, "dialogue": dialogue}

def add_recent_memory(session, **values):
    updated = _dict(session)
    memory = recent_memory(updated)
    entry = {"player_input": values.get("player_input", "")[:500]}
    entry["npc_id"] = values.get("npc_id", "")
    entry["npc_line"] = values.get("npc_line", "")[:500]
    memory["turns"] = [*memory["turns"], entry][-12:]
    if entry["npc_id"] or entry["npc_line"]:
        memory["dialogue"] = [*memory["dialogue"], entry][-20:]
    runtime = _dict(updated.get("runtime_state"))
    runtime["recent_memory"] = memory
    updated["runtime_state"] = runtime
    return updated
