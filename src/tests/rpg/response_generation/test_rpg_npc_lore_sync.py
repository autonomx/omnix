from __future__ import annotations

from app.rpg.narrative_engine import (
    CampaignBibleSnapshot,
    VisibilityClass,
    campaign_bible_evidence,
)
from app.rpg.session.genesis import turn_grounding
from app.rpg.session.genesis.npc_lore_projection import ensure_encountered_npc_lore


def _session() -> dict:
    return {
        "manifest": {"session_id": "campaign:bran-bio"},
        "state": {"current_location": "Rusty Flagon Tavern"},
        "simulation_state": {
            "tick": 7,
            "present_npc_state": {
                "location:rusty-flagon-tavern": ["npc:Bran"],
            },
        },
    }


def _empty_bible() -> dict:
    return {
        "canon_revision": 0,
        "documents": [],
        "entities": {},
        "discovery_state": {"pages": {}, "entities": {}, "discoveries": []},
    }


def test_encountered_bran_gets_one_player_known_bio_and_dossier() -> None:
    updated, ensured, created, changed = ensure_encountered_npc_lore(
        _empty_bible(),
        _session(),
        canon_revision=1,
    )

    assert changed is True
    assert ensured == ("npc:Bran",)
    assert created == ("npc:Bran",)
    bran = updated["entities"]["npc:Bran"]
    assert bran["kind"] == "npc"
    assert bran["profile_authority"] == "campaign_bible"
    assert bran["visibility"] == "player_known"
    assert "watches debts carefully" in bran["description"]
    assert bran["provenance"]["first_seen_tick"] == 7

    document = updated["documents"][0]
    assert document["document_id"] == "lore:npc:bran"
    assert document["topic_id"] == "npcs"
    assert document["title"] == "Bran"
    assert document["visibility"] == "player_known"
    assert "watches debts carefully" in document["full_text"]
    assert "old mill debts" not in document["full_text"].casefold()
    assert updated["discovery_state"]["pages"][document["document_id"]] == "learned"
    assert updated["discovery_state"]["entities"]["npc:Bran"] == "learned"

    unchanged, repeated_ids, repeated_created, repeated = ensure_encountered_npc_lore(
        updated,
        _session(),
        canon_revision=2,
    )
    assert repeated is False
    assert repeated_ids == ("npc:Bran",)
    assert repeated_created == ()
    assert len(unchanged["documents"]) == 1


def test_encountered_npc_bio_is_searchable_gameplay_evidence() -> None:
    bible, _ensured, _created, _changed = ensure_encountered_npc_lore(
        _empty_bible(),
        _session(),
        canon_revision=3,
    )
    snapshot = CampaignBibleSnapshot(
        campaign_id="campaign:bran-bio",
        revision=3,
        content_hash="sha256:bran-bio",
        document=bible,
        provenance={"source": "test"},
        consistency_report={},
        completeness={},
    )
    evidence = campaign_bible_evidence(snapshot)
    bran_document = next(
        record
        for record in evidence
        if record.metadata.get("document_id") == "lore:npc:bran"
    )

    assert bran_document.visibility is VisibilityClass.PLAYER_KNOWN
    assert "watches debts carefully" in bran_document.content
    assert "npc:Bran" in bran_document.entity_refs


def test_turn_grounding_syncs_speaking_npc_before_research(monkeypatch) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_sync(campaign_id, session, *, explicit_npc_ids=(), database=None):
        calls.append((campaign_id, tuple(explicit_npc_ids)))
        return dict(session), {
            "mode": "postgresql_authority",
            "persisted": True,
            "changed": True,
            "encountered_npc_ids": ["npc:Bran"],
            "created_npc_ids": ["npc:Bran"],
        }

    monkeypatch.setattr(turn_grounding, "sync_encountered_npc_lore", fake_sync)
    monkeypatch.setattr(turn_grounding, "runtime_evidence", lambda _result: ())
    monkeypatch.setattr(turn_grounding, "load_campaign_bible_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(turn_grounding, "research_campaign_turn", lambda **kwargs: None)

    packet = turn_grounding.build_turn_grounding_packet(
        {
            "session": _session(),
            "resolved_result": {"response_mode": "dialogue"},
            "turn_id": "turn:7",
        },
        campaign_id="campaign:bran-bio",
        player_input="How are you?",
        speaker_id="npc:Bran",
        actor_ids=("npc:Bran",),
        runtime_only=True,
    )

    assert calls and calls[0][0] == "campaign:bran-bio"
    assert set(calls[0][1]) == {"npc:Bran"}
    assert packet.metadata["npc_lore_persisted"] is True
    assert packet.metadata["npc_lore_changed"] is True
    assert packet.metadata["created_npc_lore_ids"] == ["npc:Bran"]
    assert packet.metadata["runtime_only"] is True
