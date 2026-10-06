def normalize_event(event):
    return {
        "type": event.get("type"),
        "actor": event.get("source"),
        "target": event.get("target"),
        "data": event
    }