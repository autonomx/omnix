"""Debug System - Logs all events for debugging and development.

Subscribes to:
- "*": Wildcard - logs all events

Priority: 20 (runs last to observe final state of all events)
"""


def on_any_event(session, event):
    """Log all events to stdout.
    
    Format: [EVENT] {event_type} {event_details}
    """
    etype = event.get("type", "unknown")
    print(f"[EVENT] {etype}: {dict(event)}")


def register(bus, session):
    """Register debug system handlers with the event bus.
    
    Priority 20 ensures debug logging runs last to observe final state.
    Disabled by default - call register_debug(bus, session) to enable.
    """
    bus.subscribe("*", on_any_event, priority=20)