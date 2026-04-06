"""Phase 12.6 — Unit tests for character card compatibility layer."""
from app.rpg.compat.character_cards import (
    export_canonical_character_card,
    import_external_character_card,
)


def test_import_external_character_card_basic():
    card = {
        "name": "Captain Elira",
        "description": "Veteran city guard commander",
        "personality": "Dry and disciplined",
        "data": {
            "tags": ["guard", "authority"],
            "tone": "dry",
        },
    }
    result = import_external_character_card(card)
    assert result["canonical_seed"]["name"] == "Captain Elira"
    assert "guard" in result["canonical_seed"]["traits"]
    assert result["personality_seed"]["tone"] == "dry"


def test_import_external_character_card_missing_fields():
    card = {}
    result = import_external_character_card(card)
    assert result["canonical_seed"]["name"] == "Unknown Character"
    assert result["canonical_seed"]["description"] == ""


def test_import_external_character_card_nested_data():
    card = {
        "data": {
            "name": "Sir Aldric",
            "description": "A noble knight",
            "personality": "Honourable and brave",
            "tags": ["knight", "noble"],
        },
    }
    result = import_external_character_card(card)
    assert result["canonical_seed"]["name"] == "Sir Aldric"
    assert result["canonical_seed"]["description"] == "A noble knight"
    assert "knight" in result["canonical_seed"]["traits"]


def test_import_external_character_card_duplicate_tags():
    card = {
        "name": "Test",
        "description": "Test",
        "data": {
            "tags": ["warrior", "Warrior", "WARRIOR", "mage"],
        },
    }
    result = import_external_character_card(card)
    # Duplicate tags should be deduplicated
    assert len(result["canonical_seed"]["traits"]) <= 2


def test_export_canonical_character_card_basic():
    character = {
        "name": "Captain Elira",
        "description": "Veteran commander",
        "role": "guard_captain",
        "traits": ["guard", "authority"],
        "personality": {
            "summary": "Dry and practical",
            "archetype": "authority",
            "tone": "dry",
            "style_tags": ["disciplined"],
        },
        "visual_identity": {
            "style": "rpg-portrait",
            "model": "default",
            "base_prompt": "Captain Elira, guard captain",
        },
        "appearance": {
            "profile": {
                "current_summary": "Veteran commander in city guard armor",
            }
        },
        "card": {
            "summary": "Veteran commander",
            "badge": "City Guard",
        },
    }
    result = export_canonical_character_card(character)
    assert result["name"] == "Captain Elira"
    assert result["data"]["role"] == "guard_captain"
    assert result["data"]["badge"] == "City Guard"


def test_export_canonical_character_card_minimal():
    character = {}
    result = export_canonical_character_card(character)
    assert result["spec"] == "rpg-canonical-card"
    assert result["spec_version"] == "1.0"
    assert result["name"] == "Unknown Character"


def test_import_export_roundtrip():
    """Test that importing then exporting preserves key data."""
    original_card = {
        "name": "Mage Zara",
        "description": "A powerful sorceress",
        "personality": "Wise and enigmatic",
        "data": {
            "role": "mage",
            "tags": ["magic", "sorceress"],
            "tone": "mystical",
        },
    }
    imported = import_external_character_card(original_card)
    # Build a minimal character from imported seed
    character = {
        "name": imported["canonical_seed"]["name"],
        "description": imported["canonical_seed"]["description"],
        "role": imported["canonical_seed"]["role"],
        "traits": imported["canonical_seed"]["traits"],
        "personality": imported["personality_seed"],
        "visual_identity": imported["visual_seed"],
        "appearance": {
            "profile": {
                "current_summary": imported["appearance_seed"]["current_summary"],
            }
        },
        "card": {},
    }
    exported = export_canonical_character_card(character)
    assert exported["name"] == "Mage Zara"
    assert exported["description"] == "A powerful sorceress"