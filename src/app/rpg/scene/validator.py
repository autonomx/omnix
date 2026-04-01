def validate_scene(output, grounding):
    text = output.lower()

    for entity in grounding["entities"]:
        if entity["id"] not in text:
            continue

    # Simple hallucination detection
    for word in ["dragon", "spaceship", "laser"]:
        if word in text:
            return False

    return True