"""Phase 3D — Incident engine unit tests."""

from __future__ import annotations

from app.rpg.creator.world_incidents import (
    compute_incident_diff,
    compute_policy_reaction_diff,
    decay_incidents,
    generate_policy_reactions,
    merge_incidents,
    spawn_incidents_from_state_diff,
)


def _sample_diff():
    return {
        "threads_changed": [
            {
                "id": "thr_market",
                "before": {"pressure": 3, "status": "active"},
                "after": {"pressure": 4, "status": "critical"},
            }
        ],
        "locations_changed": [
            {
                "id": "loc_docks",
                "before": {"heat": 3, "status": "active"},
                "after": {"heat": 4, "status": "hot"},
            }
        ],
        "factions_changed": [
            {
                "id": "fac_knives",
                "before": {"pressure": 2, "status": "watchful"},
                "after": {"pressure": 3, "status": "strained"},
            }
        ],
    }


def test_spawn_incidents_from_state_diff():
    incidents = spawn_incidents_from_state_diff(_sample_diff())
    ids = {x["incident_id"] for x in incidents}
    assert "inc_thr_market_critical" in ids
    assert "inc_loc_docks_hot" in ids
    assert "inc_fac_knives_strained" in ids


def test_generate_policy_reactions():
    reactions = generate_policy_reactions(_sample_diff())
    ids = {x["reaction_id"] for x in reactions}
    assert "rxn_fac_knives_crackdown" in ids


def test_merge_incidents_dedupes():
    current = [{"incident_id": "inc_a", "type": "thread_crisis", "duration": 2}]
    new = [{"incident_id": "inc_a", "type": "thread_crisis", "duration": 1}]
    merged = merge_incidents(current, new)
    assert len(merged) == 1
    assert merged[0]["incident_id"] == "inc_a"


def test_decay_incidents_removes_expired():
    incidents = [
        {"incident_id": "inc_a", "duration": 2},
        {"incident_id": "inc_b", "duration": 1},
    ]
    decayed = decay_incidents(incidents)
    ids = {x["incident_id"] for x in decayed}
    assert "inc_a" in ids
    assert "inc_b" not in ids


def test_compute_incident_diff_shape():
    before = [{"incident_id": "inc_a", "duration": 2}]
    after = [{"incident_id": "inc_b", "duration": 2}]
    diff = compute_incident_diff(before, after)
    assert diff["added"] == ["inc_b"]
    assert diff["removed"] == ["inc_a"]
    assert diff["changed"] == []


def test_compute_policy_reaction_diff_shape():
    before = [{"reaction_id": "rxn_a"}]
    after = [{"reaction_id": "rxn_b"}]
    diff = compute_policy_reaction_diff(before, after)
    assert diff["added"] == ["rxn_b"]
    assert diff["removed"] == ["rxn_a"]