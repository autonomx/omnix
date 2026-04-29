from app.rpg.profiles import dynamic_npc_profiles as profiles
from app.rpg.profiles.dynamic_npc_profiles import (
    ensure_dynamic_npc_profile,
    load_npc_profile,
)
from app.rpg.profiles.profile_drafts import (
    approve_profile_draft,
    create_pending_profile_draft,
    load_profile_draft,
    reject_profile_draft,
    validate_draft_for_approval,
)


def test_create_pending_profile_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )

    result = create_pending_profile_draft("npc:Mira", tick=2)

    assert result["drafted"] is True
    assert result["status"] == "pending_approval"
    draft = load_profile_draft("npc:Mira")
    assert draft["status"] == "pending_approval"
    assert draft["draft"]["biography"]["full_biography"]


def test_approve_profile_draft_merges_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )
    create_pending_profile_draft("npc:Mira", tick=2)

    approved = approve_profile_draft("npc:Mira", tick=3)

    assert approved["approved"] is True
    profile = load_npc_profile("npc:Mira")
    assert profile["origin"] == "llm_drafted_from_scaffold"
    assert profile["biography"]["full_biography"]
    assert profile["card_edit_state"]["last_edited_by"] == "llm_draft_approved"
    assert profile["card_edit_state"]["revision"] == 2

    draft = load_profile_draft("npc:Mira")
    assert draft["status"] == "approved"


def test_reject_profile_draft_marks_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "DEFAULT_PROFILE_ROOT", tmp_path)

    ensure_dynamic_npc_profile(
        npc_id="npc:Mira",
        name="Mira",
        identity_arc="cautious_mediator",
        current_role="Cautious mediator",
        tick=1,
    )
    create_pending_profile_draft("npc:Mira", tick=2)

    rejected = reject_profile_draft("npc:Mira", tick=3)

    assert rejected["rejected"] is True
    draft = load_profile_draft("npc:Mira")
    assert draft["status"] == "rejected"


def test_draft_validator_warns_on_unbacked_world_fact():
    validation = validate_draft_for_approval({
        "biography": {
            "short_summary": "Mira is calm.",
            "full_biography": "Mira knows the king's secret murder plot.",
            "public_reputation": "",
            "private_notes": "",
        },
        "history": {
            "background": "",
            "major_life_events": [],
            "recent_events": [],
        },
        "personality": {
            "traits": ["cautious"],
            "temperament": "measured",
            "speech_style": "calm",
            "risk_tolerance": "low",
            "conflict_style": "diplomatic",
        },
    })

    assert validation["valid"] is True
    assert validation["warnings"]
    assert validation["warnings"][0]["kind"] == "possible_unbacked_world_fact"
