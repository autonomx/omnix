from __future__ import annotations


def topic_tags(player_input: str, resolved_action_type: str, facts: list[dict[str, str]]) -> list[str]:
    text = f"{player_input} {resolved_action_type}".lower()
    tags: set[str] = set()
    if facts or any(term in text for term in ("remember", "name", "called", "trail name")):
        tags.add("identity")
    if any(term in text for term in ("rumor", "rumour", "gossip", "heard")):
        tags.add("rumor")
    if any(term in text for term in ("bandit", "road", "quarry", "clue")):
        tags.add("quest_clue")
    commerce_terms = ("buy", "sell", "price", "silver", "gold", "room", "ration")
    if any(term in text for term in commerce_terms):
        tags.add("commerce")
    if "dialogue" in resolved_action_type.lower() or "npc" in resolved_action_type.lower():
        tags.add("dialogue")
    return sorted(tags)
