"""Scene System - Tracks events for scene generation and narrative context.

Subscribes to:
- "*": Wildcard - all events are recorded for scene generation

Priority: 5 (runs after emotion but before memory for narrative richness)

Includes event importance filtering to focus on narratively significant events.
"""


def on_any_event(session, event):
    """Record all events for scene generation.
    
    Events are appended to the session's _scene_events list
    for use by the scene generator.
    
    Note: The event from the EventBus is a MappingProxyType (immutable).
    We convert it to a mutable dict for downstream systems that may
    expect mutable dicts.
    """
    if not hasattr(session, "_scene_events"):
        session._scene_events = []
    
    session._scene_events.append(dict(event))


def get_scene_events(session, director=None):
    """Get events for scene generation with optional importance filtering.
    
    Args:
        session: The current game session.
        director: Optional StoryDirector for narrative filtering.
        
    Returns:
        List of events, filtered for narrative importance if director is provided.
    """
    events = getattr(session, '_scene_events', [])
    
    if director is not None:
        # Apply narrative importance filtering
        from rpg.story.director import select_events_for_scene
        return select_events_for_scene(events, director)
    
    return events


def register(bus, session):
    """Register scene system handlers with the event bus.
    
    Priority 5 ensures scene recording runs after combat (-10) and emotion (0)
    but before memory (10).
    """
    bus.subscribe("*", on_any_event, priority=5)
