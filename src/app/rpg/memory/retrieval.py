def score_event(event, query):
    score = 0

    if query.get("target") == event.get("target"):
        score += 2

    if query.get("type") == event.get("type"):
        score += 1

    return score


def retrieve(npc, query, k=5):
    scored = []

    for e in npc.memory:
        scored.append((score_event(e, query), e))

    scored.sort(reverse=True, key=lambda x: x[0])

    return [e for score, e in scored[:k] if score > 0]