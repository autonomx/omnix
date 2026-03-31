def soft_validate(action, rules):
    """
    Validate action with soft rules - allows actions but with consequences.
    Returns (is_valid, consequence) tuple.
    """
    # Placeholder for rule validation
    # In real implementation, check against game rules but allow violations
    # with narrative consequences instead of hard rejection

    violations = []

    # Example soft rules
    if action.get("type") == "attack" and action.get("target") == "ally":
        violations.append("Attacking an ally is frowned upon")

    if violations:
        return False, f"Action violates rules: {', '.join(violations)}. Proceed with consequences?"
    else:
        return True, None


def should_override_rules(action, context):
    """
    LLM adjudicates rule overrides for narrative interest.
    Returns whether to allow the rule-breaking action.
    """
    # Placeholder for LLM-driven rule adjudication
    # In real implementation, evaluate if breaking rules serves narrative interest

    # Simple heuristic: allow if tension is high
    tension = context.get("tension", 0.5)
    if tension > 0.8:
        return True  # Allow for dramatic effect

    return False