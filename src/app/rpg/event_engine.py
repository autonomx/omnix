def inject_event(session, director_output):
    """
    Inject dynamic events like ambushes, betrayals, discoveries for tension and surprise.
    """
    # Placeholder for event injection logic
    # In real implementation, based on director_output and session state,
    # decide whether to inject events and what type

    if director_output.event:
        # Process the event from director_output
        event_type = director_output.event
        if event_type == "ambush":
            # Inject ambush event
            session.current_event = {
                "type": "ambush",
                "description": "Enemies spring from hiding!",
                "consequences": ["combat_engaged"]
            }
        elif event_type == "betrayal":
            session.current_event = {
                "type": "betrayal",
                "description": "An ally turns against you!",
                "consequences": ["relationship_change", "combat_engaged"]
            }
        elif event_type == "discovery":
            session.current_event = {
                "type": "discovery",
                "description": "You find something unexpected!",
                "consequences": ["new_information"]
            }

        return session.current_event

    return None