from __future__ import annotations

from app.rpg.session.genesis.world_forge_dossiers import (
    DOSSIER_SCHEMA_VERSION,
    dossier_prompt_contract,
    project_entity_dossier,
    validate_entity_dossier,
)
from app.rpg.worlds.authoring_presentations import entity_card


def test_legacy_race_projects_to_multi_section_dossier_without_migration() -> None:
    row = {
        "id": "race:aetherborn",
        "name": "Aetherborn",
        "kind": "race",
        "description": (
            "Aetherborn are manifestations of raw aether shaped into conscious form. "
            "They are not born in the mortal sense, but coalesce where the Weave is strongest."
        ),
        "origin": (
            "The first Aetherborn appeared when the Great Weave fractured above the old capital.\n\n"
            "Later generations formed around resonant anchors and inherited fragments of ancient memory."
        ),
        "appearance": "Their bodies are semi-ethereal, luminous, and marked by shifting constellations.",
        "cultures": ["The Aether Conclave", "The Veiled Accord"],
        "traits": ["Aetheric form", "Essence sight", "Weave attunement"],
        "lifespan": "300-800 years",
        "homelands": ["region:aether_expanse"],
        "languages": ["Common", "Aetheric Cant"],
        "visibility": "public",
    }

    short_summary, dossier = project_entity_dossier(
        row,
        card_type="races",
        entity_id="race:aetherborn",
    )

    assert short_summary.startswith("Aetherborn are manifestations")
    assert dossier["schema_version"] == DOSSIER_SCHEMA_VERSION
    assert dossier["generated_from_legacy"] is True
    assert [section["id"] for section in dossier["sections"]][:4] == [
        "overview",
        "origin",
        "appearance",
        "culture",
    ]
    origin = next(section for section in dossier["sections"] if section["id"] == "origin")
    assert len(origin["paragraphs"]) == 2
    assert {fact["label"] for fact in dossier["quick_facts"]} >= {"Lifespan", "Visibility"}
    assert dossier["related_entity_ids"] == ["region:aether_expanse"]
    assert validate_entity_dossier(dossier) == ()


def test_explicit_dossier_preserves_editorial_sections_and_quote() -> None:
    row = {
        "id": "npc:velith",
        "name": "Oracle Veylith",
        "description": "An oracle who remembers possible dawns.",
        "dossier": {
            "schema_version": DOSSIER_SCHEMA_VERSION,
            "subtitle": "The thought that remembers the dawn",
            "quote": {
                "text": "We are the breath between the stars.",
                "attribution": "Oracle Veylith",
            },
            "quick_facts": [{"label": "Role", "value": "Oracle"}],
            "sections": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "paragraphs": [
                        "Veylith advises the Aether Conclave when ordinary prophecy fails.",
                        "Her visions arrive as memories of futures that have not happened.",
                    ],
                },
                {
                    "id": "current-situation",
                    "title": "Current Situation",
                    "paragraphs": ["She has withdrawn from court after seeing the same ending three times."],
                },
            ],
            "related_entity_ids": ["faction:aether_conclave"],
        },
    }

    _summary, dossier = project_entity_dossier(
        row,
        card_type="npcs",
        entity_id="npc:velith",
    )

    assert dossier["generated_from_legacy"] is False
    assert dossier["subtitle"] == "The thought that remembers the dawn"
    assert dossier["quote"]["attribution"] == "Oracle Veylith"
    assert len(dossier["sections"][0]["paragraphs"]) == 2
    assert dossier["related_entity_ids"] == ["faction:aether_conclave"]
    assert validate_entity_dossier(dossier) == ()


def test_authoring_card_keeps_compact_summary_and_exposes_full_dossier() -> None:
    card = entity_card(
        {
            "id": "location:starfall_archives",
            "name": "The Starfall Archives",
            "description": "A hidden sanctum built around a fallen star.",
            "sensory_profile": "Cold silver light gathers on black shelves while the air tastes of rain.",
            "history": "The archive was sealed after its custodians disagreed about a forbidden prophecy.",
            "secrets": ["The fallen star is still conscious"],
            "hooks": ["A missing scholar left a map in the restricted stacks"],
            "region_id": "region:aether_expanse",
        },
        card_type="locations",
        kind="location",
        index=0,
    )

    assert card["summary"] == "A hidden sanctum built around a fallen star."
    assert card["short_summary"] == card["summary"]
    assert card["dossier"]["schema_version"] == DOSSIER_SCHEMA_VERSION
    assert {section["id"] for section in card["dossier"]["sections"]} >= {
        "overview",
        "atmosphere",
        "history",
        "secrets",
        "hooks",
    }


def test_legacy_place_projects_registry_data_into_readable_dossier_sections() -> None:
    _summary, dossier = project_entity_dossier(
        {
            "id": "ent:places:005",
            "name": "Altair Elite Residential Blocks",
            "description": "A sealed luxury enclave for Altair's corporate elite.",
            "region_id": "region:005",
            "registry_role": "Luxury Enclave",
            "access_routes": {
                "primary_access": "Controlled corporate sky-lifts and dedicated maglev lines",
                "secondary_access": "Restricted private aerial drones and maintenance tunnels",
            },
            "current_pressure": "Extreme socioeconomic isolation and perpetual corporate surveillance.",
            "observable_evidence": {
                "visuals": "Chromasteel towers and immaculate hydroponic gardens",
                "auditory": "Muted life-support hum and synthesized ambient music",
            },
            "registry_distinction": "The residential districts housing Altair's global corporate elite.",
        },
        card_type="places",
        entity_id="ent:places:005",
    )

    sections = {section["id"]: section for section in dossier["sections"]}
    assert set(sections) >= {"overview", "setting", "access", "atmosphere", "pressures", "distinction"}
    assert sections["access"]["title"] == "Access and Security"
    assert sections["access"]["paragraphs"] == [
        "Primary Access: Controlled corporate sky-lifts and dedicated maglev lines.",
        "Secondary Access: Restricted private aerial drones and maintenance tunnels.",
    ]
    assert sections["atmosphere"]["title"] == "Atmosphere and Evidence"


def test_prompt_contract_requests_domain_specific_multi_paragraph_content() -> None:
    contract = dossier_prompt_contract("races")

    assert contract["schema_version"] == DOSSIER_SCHEMA_VERSION
    sections = contract["entity_fields"]["dossier"]["sections"]
    assert [section["id"] for section in sections][:5] == [
        "overview",
        "origin",
        "appearance",
        "culture",
        "abilities",
    ]
    assert contract["content_targets"]["standard_words"] == "350-800"
    assert contract["content_targets"]["paragraphs_per_substantive_section"] == "1-3"
