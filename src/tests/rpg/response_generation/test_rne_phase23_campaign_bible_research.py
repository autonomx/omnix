from __future__ import annotations

from copy import deepcopy

from app.rpg.session.genesis.compiler import compile_campaign_genesis
from app.rpg.session.genesis.contract import CampaignGenesisContract
from app.rpg.session.genesis.hermes_campaign_research import (
    research_campaign_turn,
)
from app.rpg.session.genesis.materialization import (
    materialize_world_forge_into_session,
)
from app.rpg.session.genesis.world_forge_pipeline import (
    run_campaign_world_forge,
)
from app.rpg.session.narrative_engine_bridge import (
    canonicalize_direct_dialogue_result,
)


def _campaign() -> tuple[CampaignGenesisContract, dict]:
    contract = CampaignGenesisContract.model_validate(
        {
            "campaign_template": "summoned_heroes",
            "genre": "portal_fantasy",
            "tone": "fractured mythic fantasy",
            "world_options": {
                "starting_location": "vanta_gate",
                "seed": 112,
            },
            "world_forge": {"depth": "standard"},
        }
    )
    compiled = compile_campaign_genesis(contract)
    forge = run_campaign_world_forge(
        contract,
        campaign_id="campaign:phase23",
        compiled_genesis=compiled,
    )
    assert forge.launch_ready is True
    session = {
        "manifest": {"session_id": "campaign:phase23"},
        "state": {},
        "runtime_state": {},
        "setup_payload": {},
    }
    return contract, materialize_world_forge_into_session(
        session,
        contract,
        forge,
    )


def test_hermes_selects_at_most_five_cited_campaign_topics() -> None:
    _, session = _campaign()
    packet = research_campaign_turn(
        campaign_id="campaign:phase23",
        query=(
            "Vexira explains summoned heroes, the Unmaker, the Academy, "
            "Aertos, Solara, and the Vanta Gate"
        ),
        session=session,
        speaker_id="npc:vexira_umbra",
        actor_ids=("npc:vexira_umbra",),
        entity_ids=(
            "npc:vexira_umbra",
            "location:vanta_gate",
            "faction:silent_chorus",
        ),
        max_topics=5,
    )
    assert packet is not None
    assert 1 <= len(packet.result.sources) <= 5
    assert len(packet.result.sources) == len(packet.topic_titles)
    assert all(
        source.citation.startswith("campaign-bible:campaign:phase23@1#")
        for source in packet.result.sources
    )
    assert packet.result.metadata["read_only"] is True
    assert packet.result.metadata["may_mutate_campaign_bible"] is False
    assert packet.snapshot.revision == 1


def test_private_vexira_secret_is_filtered_until_vexira_is_speaker() -> None:
    _, session = _campaign()
    query = "exact hero who killed the previous Unmaker"
    player_packet = research_campaign_turn(
        campaign_id="campaign:phase23",
        query=query,
        session=session,
        max_topics=5,
    )
    assert player_packet is not None
    assert all(
        "exact hero" not in finding.content.casefold()
        for finding in player_packet.result.findings
    )

    speaker_packet = research_campaign_turn(
        campaign_id="campaign:phase23",
        query=query,
        session=session,
        speaker_id="npc:vexira_umbra",
        actor_ids=("npc:vexira_umbra",),
        entity_ids=("npc:vexira_umbra",),
        max_topics=5,
    )
    assert speaker_packet is not None
    private = [
        finding
        for finding in speaker_packet.result.findings
        if "exact hero" in finding.content.casefold()
    ]
    assert private
    assert private[0].visibility.value == "npc_private"
    assert private[0].known_by == ("npc:vexira_umbra",)


def test_direct_dialogue_uses_bible_hermes_and_preserves_session_state() -> None:
    _, session = _campaign()
    before = deepcopy(session)
    result = {
        "ok": True,
        "turn_id": "turn:phase23:1",
        "session": session,
        "npc": {
            "speaker": "Vexira Umbra",
            "speaker_id": "npc:vexira_umbra",
            "line": "The gate remembers the last hero who came too early.",
        },
        "scene": {
            "location_id": "location:vanta_gate",
            "summary": "The Vanta Gate pulses beneath mirror traps.",
        },
        "resolved_result": {
            "response_mode": "dialogue",
            "success": True,
        },
    }
    published = canonicalize_direct_dialogue_result(
        result,
        session_id="campaign:phase23",
        player_input="Tell me about the summoning and the Unmaker.",
    )
    canonical = published["canonical_narrative_response"]
    assert canonical["generation"]["hermes_used"] is True
    metadata = canonical["generation"]["metadata"]
    assert 1 <= metadata["canon_topic_count"] <= 5
    assert metadata["campaign_bible_revision"] == 1
    assert published["narrative_grounding_footer"]["grounding_passed"] is True
    assert "canon topics used" in published["narrative_grounding_footer"]["label"]
    assert published["session"] == before
