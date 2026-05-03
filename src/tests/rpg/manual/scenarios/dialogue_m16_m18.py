from __future__ import annotations

from typing import Any, Dict

DIALOGUE_M16_M18_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "npc_can_discuss_lore_they_know": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
                "known_by": ["bran"],
                "tags": ["bandit"],
            }
        ],
        "turns": ["I ask Bran what he knows about the Red Sashes."],
        "checks": [
            {
                "type": "dialogue_context",
                "npc_id": "bran",
                "topic_lore_id": "lore:red_sashes",
                "expected_can_discuss": True,
                "expected_lore_id": "lore:red_sashes",
                "expected_must_mark_as_rumor": True,
            }
        ],
    },
    "npc_cannot_discuss_secret_lore_they_do_not_know": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:bran_debt",
                "title": "Bran's Hidden Debt",
                "truth_status": "secret",
                "known_by": ["bran"],
            }
        ],
        "turns": ["I ask Mira about Bran's hidden debt."],
        "checks": [
            {
                "type": "dialogue_context",
                "npc_id": "mira",
                "topic_lore_id": "lore:bran_debt",
                "expected_can_discuss": False,
            }
        ],
    },
    "npc_marks_unverified_lore_as_rumor": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
                "known_by": ["bran"],
            }
        ],
        "turns": ["I ask Bran if the Red Sashes rumor is confirmed."],
        "checks": [
            {
                "type": "dialogue_context",
                "npc_id": "bran",
                "topic_lore_id": "lore:red_sashes",
                "expected_can_discuss": True,
                "expected_must_mark_as_rumor": True,
            }
        ],
    },
    "npc_discusses_arc_if_memory_links_them": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
                "known_by": ["bran"],
            }
        ],
        "setup_story_arc_transitions": [
            {
                "action": "start",
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "stage": "rumors",
                "pressure": 20,
                "links": {"lore": ["lore:red_sashes"], "entities": ["bran"]},
            }
        ],
        "turns": ["I ask Bran about the bandit pressure."],
        "checks": [
            {
                "type": "dialogue_context",
                "npc_id": "bran",
                "arc_id": "arc:bandit_pressure",
                "expected_can_discuss": True,
                "expected_arc_id": "arc:bandit_pressure",
            }
        ],
    },
    "npc_refuses_arc_topic_if_social_hostile": {
        "setup_social_state": {"relationships": {"bran": {"trust": -20, "hostility": 60}}},
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
                "known_by": ["bran"],
            }
        ],
        "turns": ["I demand Bran tell me about the Red Sashes."],
        "checks": [
            {
                "type": "dialogue_context",
                "npc_id": "bran",
                "topic_lore_id": "lore:red_sashes",
                "expected_can_discuss": False,
            }
        ],
    },
    "rumor_spreads_to_audible_npc": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "setup_rumor_propagations": [
            {
                "speaker_id": "bran",
                "lore_id": "lore:red_sashes",
                "summary": "The Red Sashes are active again.",
                "explicit_hearers": ["mira"],
            }
        ],
        "turns": ["I check whether Mira heard Bran's rumor."],
        "checks": [
            {
                "type": "rumor_memory",
                "subject_id": "mira",
                "expected_lore_id": "lore:red_sashes",
                "tags": ["rumor"],
            }
        ],
    },
    "rumor_does_not_spread_through_blocked_wall": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "turns": ["I test rumor propagation without hearers."],
        "checks": [
            {
                "type": "rumor_propagation",
                "speaker_id": "bran",
                "lore_id": "lore:red_sashes",
                "summary": "The Red Sashes are active again.",
                "explicit_hearers": [],
                "expected_ok": True,
                "expected_truth_promoted": False,
            },
            {
                "type": "rumor_truth_status",
                "lore_id": "lore:red_sashes",
                "expected_truth_status": "rumor",
            },
        ],
    },
    "rumor_does_not_promote_to_truth": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "setup_rumor_propagations": [
            {
                "speaker_id": "bran",
                "lore_id": "lore:red_sashes",
                "summary": "The Red Sashes are active again.",
                "explicit_hearers": ["mira"],
            }
        ],
        "turns": ["I check whether the rumor became truth."],
        "checks": [
            {
                "type": "rumor_truth_status",
                "lore_id": "lore:red_sashes",
                "expected_truth_status": "rumor",
            }
        ],
    },
    "rumor_hearer_can_discuss_as_rumor": {
        "setup_lore_transitions": [
            {
                "action": "upsert",
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "setup_rumor_propagations": [
            {
                "speaker_id": "bran",
                "lore_id": "lore:red_sashes",
                "summary": "The Red Sashes are active again.",
                "explicit_hearers": ["mira"],
            }
        ],
        "turns": ["I ask Mira what she heard about the Red Sashes."],
        "checks": [
            {
                "type": "dialogue_context",
                "npc_id": "mira",
                "topic_lore_id": "lore:red_sashes",
                "expected_can_discuss": True,
                "expected_lore_id": "lore:red_sashes",
                "expected_must_mark_as_rumor": True,
            }
        ],
    },
}