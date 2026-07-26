from app.rpg.session.genesis.canon_audit import audit_generated_canon
from app.rpg.session.genesis.world_forge_causal_audit import audit_causal_canon
from app.rpg.session.genesis.world_forge_generation import GeneratedTopic


def _history(*events: dict) -> GeneratedTopic:
    return GeneratedTopic(topic_id="history_timeline", entities=events)


def _places(*places: dict) -> GeneratedTopic:
    return GeneratedTopic(topic_id="places", entities=places)


def _links(*links: dict) -> GeneratedTopic:
    return GeneratedTopic(topic_id="causal_links", entities=links)


def test_valid_causal_canon_passes_without_destructive_patches() -> None:
    topics = (
        _history(
            {
                "id": "event:war",
                "kind": "historical_event",
                "legacy_status": "continuing",
                "present_day_legacies": {"trace": "The bridge fortress remains."},
                "start_year": 411,
            }
        ),
        _places(
            {
                "id": "place:ironford",
                "kind": "place",
                "founding_event_ids": ["event:war"],
            }
        ),
        _links(
            {
                "id": "causal:war_to_ironford",
                "kind": "causal_link",
                "cause_event_ids": ["event:war"],
                "effect_id": "place:ironford",
                "effect_type": "founded",
                "mechanism": "The army required a permanent fortified river crossing.",
                "persistence": "continuing",
                "start_year": 411,
                "end_year": 414,
            }
        ),
    )

    assert audit_causal_canon(topics) == ()
    report = audit_generated_canon(topics)
    assert report.passed
    assert report.patches == ()
    assert report.checks["causal_findings"] == 0


def test_causal_cycles_dates_and_mechanisms_block_publication() -> None:
    topics = (
        _history(
            {
                "id": "event:a",
                "kind": "historical_event",
                "cause_event_ids": ["event:b"],
                "legacy_status": "continuing",
                "present_day_legacies": {"trace": "A"},
                "start_year": 20,
            },
            {
                "id": "event:b",
                "kind": "historical_event",
                "cause_event_ids": ["event:a"],
                "legacy_status": "continuing",
                "present_day_legacies": {"trace": "B"},
                "start_year": 10,
            },
        ),
        _places({"id": "place:x", "kind": "place"}),
        _links(
            {
                "id": "causal:broken",
                "kind": "causal_link",
                "cause_event_ids": ["event:a"],
                "effect_id": "place:x",
                "effect_type": "founded",
                "mechanism": "Because war.",
                "persistence": "continuing",
                "start_year": 30,
                "end_year": 15,
            }
        ),
    )

    report = audit_generated_canon(topics)
    codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert "historical_causal_cycle" in codes
    assert "historical_cause_after_effect" in codes
    assert "causal_date_reversal" in codes
    assert "missing_causal_mechanism" in codes
    assert report.patches == ()


def test_launch_slice_does_not_require_deferred_causal_links() -> None:
    topics = (
        _history(
            {
                "id": "event:old_fall",
                "kind": "historical_event",
                "legacy_status": "continuing",
                "present_day_legacies": {"trace": "Inheritance law remains."},
            }
        ),
        _places(
            {
                "id": "place:capital",
                "kind": "place",
                "founding_event_ids": ["event:old_fall"],
            }
        ),
    )

    assert audit_causal_canon(topics) == ()
