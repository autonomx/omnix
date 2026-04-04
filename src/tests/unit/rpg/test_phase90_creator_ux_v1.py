"""Unit tests for Creator UX v1 — Adventure Builder endpoints and services.

Tests cover:
- Template listing endpoint
- Template payload building endpoint
- Validate endpoint
- Preview endpoint
- Start adventure endpoint
- Adventure response adapter
- Adventure builder service functions
- Enhanced validation (UX hints)
- Enriched template metadata
"""

from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Service-level imports
# ---------------------------------------------------------------------------
from app.rpg.services.adventure_builder_service import (
    ADVENTURE_PREVIEW_RESPONSE_VERSION,
    build_template_payload,
    get_templates,
    preview_setup,
    start_adventure,
    validate_setup,
)
from app.rpg.services.adventure_response_adapter import (
    ADVENTURE_START_RESPONSE_VERSION,
    adapt_start_result,
)
from app.rpg.creator.defaults import list_setup_templates
from app.rpg.creator.validation import (
    ValidationResult,
    validate_adventure_setup_payload,
    validate_setup_ux_hints,
)


# ===================================================================
# helpers
# ===================================================================


def _minimal_setup(**overrides) -> dict:
    """Return a minimal valid adventure-setup dict."""
    base = {
        "setup_id": "test_setup",
        "title": "Test Adventure",
        "genre": "fantasy",
        "setting": "A test world",
        "premise": "Testing the adventure builder system",
    }
    base.update(overrides)
    return base


def _rich_setup(**overrides) -> dict:
    """Return a setup dict with factions, locations, NPCs."""
    base = _minimal_setup()
    base.update({
        "factions": [
            {"faction_id": "fac_guard", "name": "City Guard", "description": "The law", "goals": ["Keep order"]},
            {"faction_id": "fac_thieves", "name": "Thieves Guild", "description": "Underground", "goals": ["Profit"]},
        ],
        "locations": [
            {"location_id": "loc_market", "name": "Night Market", "description": "Bustling market", "tags": ["urban"]},
            {"location_id": "loc_docks", "name": "Docks", "description": "Foggy waterfront", "tags": ["harbor"]},
        ],
        "npc_seeds": [
            {
                "npc_id": "npc_fixer",
                "name": "Mara Voss",
                "role": "fixer",
                "description": "A resourceful broker",
                "goals": ["Survive"],
                "faction_id": "fac_thieves",
                "location_id": "loc_market",
                "must_survive": True,
            },
            {
                "npc_id": "npc_detective",
                "name": "Officer Hale",
                "role": "detective",
                "description": "A weary cop",
                "goals": ["Justice"],
                "faction_id": "fac_guard",
                "location_id": "loc_docks",
                "must_survive": False,
            },
        ],
        "starting_location_id": "loc_market",
        "starting_npc_ids": ["npc_fixer", "npc_detective"],
    })
    base.update(overrides)
    return base


# ===================================================================
# Template listing tests
# ===================================================================


class TestTemplateList:
    def test_list_returns_templates(self):
        templates = get_templates()
        assert isinstance(templates, list)
        assert len(templates) >= 5
        names = [t["name"] for t in templates]
        assert "fantasy_adventure" in names
        assert "cyberpunk_heist" in names

    def test_templates_have_rich_metadata(self):
        templates = get_templates()
        for t in templates:
            assert "name" in t
            assert "genre" in t
            assert "mood" in t
            assert "label" in t
            assert "description" in t
            assert "recommended_for" in t
            assert t["label"]  # non-empty
            assert t["description"]  # non-empty

    def test_list_setup_templates_enriched(self):
        """list_setup_templates now returns richer descriptors."""
        templates = list_setup_templates()
        fantasy = next(t for t in templates if t["name"] == "fantasy_adventure")
        assert fantasy["label"] == "Fantasy Adventure"
        assert "heroic" in fantasy["description"].lower() or "fantasy" in fantasy["description"].lower()
        assert fantasy["recommended_for"]


# ===================================================================
# Template payload building tests
# ===================================================================


class TestTemplateBuild:
    def test_build_known_template(self):
        result = build_template_payload("fantasy_adventure")
        assert result["success"]
        setup = result["setup"]
        assert setup["genre"] == "fantasy"
        # Defaults should be applied
        assert "hard_rules" in setup
        assert "pacing" in setup

    def test_build_all_templates(self):
        templates = get_templates()
        for t in templates:
            result = build_template_payload(t["name"])
            assert result["success"], f"Failed to build template: {t['name']}"
            assert result["setup"]["genre"]

    def test_build_unknown_template_returns_error(self):
        result = build_template_payload("nonexistent_template")
        assert not result.get("success")


# ===================================================================
# Validation tests
# ===================================================================


class TestValidation:
    def test_valid_setup(self):
        result = validate_setup(_minimal_setup())
        assert result["success"]
        validation = result["validation"]
        assert not validation["blocking"]

    def test_missing_required_fields(self):
        result = validate_setup({"setup_id": "x"})
        assert result["success"]
        validation = result["validation"]
        assert validation["blocking"]
        codes = [i["code"] for i in validation["issues"]]
        assert "required" in codes

    def test_duplicate_npc_ids_blocking(self):
        payload = _minimal_setup(npc_seeds=[
            {"npc_id": "npc_dup", "name": "A"},
            {"npc_id": "npc_dup", "name": "B"},
        ])
        result = validate_setup(payload)
        validation = result["validation"]
        assert validation["blocking"]
        codes = [i["code"] for i in validation["issues"]]
        assert "duplicate_id" in codes

    def test_dangling_npc_faction_ref_warning(self):
        payload = _minimal_setup(npc_seeds=[
            {"npc_id": "npc_a", "name": "A", "faction_id": "nonexistent"},
        ])
        result = validate_setup(payload)
        validation = result["validation"]
        # Warnings are not blocking
        warnings = [i for i in validation["issues"] if i["severity"] == "warning"]
        assert any("dangling" in w["code"] for w in warnings)

    def test_dangling_starting_location_warning(self):
        payload = _minimal_setup(starting_location_id="loc_nowhere")
        result = validate_setup(payload)
        validation = result["validation"]
        warnings = [i for i in validation["issues"] if i["severity"] == "warning"]
        assert any("starting_location_id" in w["path"] for w in warnings)


# ===================================================================
# UX-hint validation tests
# ===================================================================


class TestUxHintValidation:
    def test_no_locations_warning(self):
        issues = validate_setup_ux_hints(_minimal_setup())
        codes = [i.code for i in issues]
        assert "no_locations" in codes

    def test_no_npcs_warning(self):
        issues = validate_setup_ux_hints(_minimal_setup())
        codes = [i.code for i in issues]
        assert "no_npcs" in codes

    def test_short_premise_warning(self):
        issues = validate_setup_ux_hints(_minimal_setup(premise="Short"))
        codes = [i.code for i in issues]
        assert "short_premise" in codes

    def test_title_equals_setting_warning(self):
        issues = validate_setup_ux_hints(_minimal_setup(title="Same", setting="Same"))
        codes = [i.code for i in issues]
        assert "title_equals_setting" in codes

    def test_too_many_starting_npcs_warning(self):
        issues = validate_setup_ux_hints(_minimal_setup(
            starting_npc_ids=["a", "b", "c", "d", "e", "f"]
        ))
        codes = [i.code for i in issues]
        assert "too_many_starting_npcs" in codes

    def test_no_starting_location_info(self):
        issues = validate_setup_ux_hints(_minimal_setup(
            locations=[{"location_id": "loc_a", "name": "A"}],
        ))
        codes = [i.code for i in issues]
        assert "no_starting_location" in codes

    def test_no_warning_when_populated(self):
        payload = _rich_setup()
        issues = validate_setup_ux_hints(payload)
        codes = [i.code for i in issues]
        assert "no_locations" not in codes
        assert "no_npcs" not in codes


# ===================================================================
# Preview tests
# ===================================================================


class TestPreview:
    def test_valid_preview(self):
        result = preview_setup(_rich_setup())
        assert result["success"]
        assert result["ok"]
        assert "validation" in result
        assert "preview" in result
        assert "resolved_context" in result

    def test_preview_resolved_context(self):
        result = preview_setup(_rich_setup())
        ctx = result["resolved_context"]
        assert ctx["location_id"] == "loc_market"
        assert "npc_fixer" in ctx["npc_ids"]
        assert "Mara Voss" in ctx["npc_names"]
        assert ctx["location_name"] == "Night Market"

    def test_preview_counts(self):
        result = preview_setup(_rich_setup())
        preview = result["preview"]
        assert "counts" in preview
        assert preview["counts"]["factions"] == 2
        assert preview["counts"]["locations"] == 2
        assert preview["counts"]["npcs"] == 2

    def test_blocking_setup_returns_ok_false(self):
        result = preview_setup({"setup_id": "x"})  # missing required
        assert result["success"]
        assert not result["ok"]
        assert result["validation"]["blocking"]

    def test_preview_auto_selects_first_location(self):
        payload = _minimal_setup(
            locations=[
                {"location_id": "loc_a", "name": "Alpha", "description": "First location", "tags": []},
                {"location_id": "loc_b", "name": "Beta", "description": "Second location", "tags": []},
            ],
        )
        result = preview_setup(payload)
        if result.get("ok"):
            ctx = result["resolved_context"]
            assert ctx["location_id"] == "loc_a"
            assert ctx["location_name"] == "Alpha"


# ===================================================================
# Start adventure tests
# ===================================================================


class TestStartAdventure:
    def test_start_minimal_setup(self):
        result = start_adventure(_minimal_setup())
        assert result["success"]
        assert result["session_id"]
        assert result["opening"]
        assert result["world"]
        assert result["player"]

    def test_start_rich_setup(self):
        result = start_adventure(_rich_setup())
        assert result["success"]
        assert result["session_id"]
        assert len(result["npcs"]) == 2
        assert result["opening"]

    def test_start_returns_generated_data(self):
        result = start_adventure(_rich_setup())
        assert "generated" in result
        gen = result["generated"]
        assert "world_frame" in gen
        assert "opening_situation" in gen
        assert "seed_npcs" in gen

    def test_start_invalid_blocks(self):
        result = start_adventure({"setup_id": "x"})  # missing required
        assert not result["success"]
        assert "validation" in result

    def test_start_from_template(self):
        tpl = build_template_payload("mystery_noir")
        assert tpl["success"]
        payload = tpl["setup"]
        payload["setup_id"] = "test_noir"
        payload["title"] = "Test Noir"
        result = start_adventure(payload)
        assert result["success"]
        assert result["world"]["genre"] == "mystery noir"


# ===================================================================
# Response adapter tests
# ===================================================================


class TestResponseAdapter:
    def test_adapt_minimal(self):
        raw = {
            "ok": True,
            "setup": {"setup_id": "s1", "metadata": {"player_name": "Hero"}},
            "generated": {
                "world_frame": {"title": "T", "genre": "fantasy", "setting": "Forest"},
                "opening_situation": {"summary": "A great adventure.", "location": "Forest", "present_actors": ["Elf"]},
                "seed_npcs": [{"npc_id": "n1", "name": "Elf", "role": "guide"}],
                "seed_factions": [],
                "seed_locations": [{"location_id": "l1", "name": "Forest"}],
            },
            "canon_summary": {"facts": [{"subject": "world", "value": "fantasy"}]},
        }
        result = adapt_start_result(raw)
        assert result["success"]
        assert result["session_id"] == "s1"
        assert "Forest" in result["opening"]
        assert result["world"]["name"] == "T"
        assert result["player"]["name"] == "Hero"
        assert len(result["npcs"]) == 1
        assert result["npcs"][0]["name"] == "Elf"

    def test_adapt_empty_generated(self):
        raw = {"ok": True, "setup": {}, "generated": {}, "canon_summary": {}}
        result = adapt_start_result(raw)
        assert result["success"]
        assert result["opening"]  # fallback text

    def test_adapt_generates_session_id(self):
        raw = {"ok": True, "setup": {}, "generated": {}, "canon_summary": {}}
        result = adapt_start_result(raw)
        assert result["session_id"]  # uuid should be generated


# ===================================================================
# Flask route integration tests
# ===================================================================


@pytest.fixture
def app():
    """Create a Flask test application with the creator blueprint."""
    from flask import Flask
    from app.rpg.creator_routes import creator_bp

    test_app = Flask(__name__)
    test_app.register_blueprint(creator_bp)
    test_app.config["TESTING"] = True
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestCreatorRoutes:
    def test_get_templates(self, client):
        resp = client.get("/api/rpg/adventure/templates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert len(data["templates"]) >= 5

    def test_build_template(self, client):
        resp = client.post(
            "/api/rpg/adventure/template",
            data=json.dumps({"template_name": "fantasy_adventure"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert data["setup"]["genre"] == "fantasy"

    def test_build_unknown_template(self, client):
        resp = client.post(
            "/api/rpg/adventure/template",
            data=json.dumps({"template_name": "unknown"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_build_template_missing_name(self, client):
        resp = client.post(
            "/api/rpg/adventure/template",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_validate_valid_setup(self, client):
        resp = client.post(
            "/api/rpg/adventure/validate",
            data=json.dumps(_minimal_setup()),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert not data["validation"]["blocking"]

    def test_validate_invalid_setup(self, client):
        resp = client.post(
            "/api/rpg/adventure/validate",
            data=json.dumps({"setup_id": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert data["validation"]["blocking"]

    def test_validate_empty_body(self, client):
        resp = client.post(
            "/api/rpg/adventure/validate",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_preview_valid_setup(self, client):
        resp = client.post(
            "/api/rpg/adventure/preview",
            data=json.dumps(_rich_setup()),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"]
        assert data["ok"]
        assert "preview" in data
        assert "resolved_context" in data

    def test_preview_blocking(self, client):
        resp = client.post(
            "/api/rpg/adventure/preview",
            data=json.dumps({"setup_id": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert not data["ok"]

    def test_start_valid_setup(self, client):
        resp = client.post(
            "/api/rpg/adventure/start",
            data=json.dumps(_rich_setup()),
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"]
        assert data["session_id"]
        assert data["opening"]

    def test_start_invalid_setup(self, client):
        resp = client.post(
            "/api/rpg/adventure/start",
            data=json.dumps({"setup_id": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert not data["success"]

    def test_start_empty_body(self, client):
        resp = client.post(
            "/api/rpg/adventure/start",
            content_type="application/json",
        )
        assert resp.status_code == 400


# ===================================================================
# End-to-end flow tests
# ===================================================================


class TestEndToEndFlow:
    """Test the full flow: template → edit → validate → preview → start."""

    def test_full_flow_from_template(self):
        # 1. List templates
        templates = get_templates()
        assert len(templates) >= 1

        # 2. Build template
        tpl_result = build_template_payload("cyberpunk_heist")
        assert tpl_result["success"]
        payload = tpl_result["setup"]

        # 3. Add required fields
        payload["setup_id"] = "e2e_test"
        payload["title"] = "E2E Cyberpunk"

        # 4. Add entities
        payload["factions"] = [
            {"faction_id": "fac_corp", "name": "MegaCorp", "description": "The corporation"},
        ]
        payload["locations"] = [
            {"location_id": "loc_hub", "name": "The Hub", "description": "Central location"},
        ]
        payload["npc_seeds"] = [
            {"npc_id": "npc_hacker", "name": "Zero", "role": "hacker", "description": "Genius",
             "faction_id": "fac_corp", "location_id": "loc_hub"},
        ]
        payload["starting_location_id"] = "loc_hub"
        payload["starting_npc_ids"] = ["npc_hacker"]

        # 5. Validate
        val_result = validate_setup(payload)
        assert not val_result["validation"]["blocking"]

        # 6. Preview
        prev_result = preview_setup(payload)
        assert prev_result["ok"]
        assert prev_result["resolved_context"]["location_name"] == "The Hub"
        assert "Zero" in prev_result["resolved_context"]["npc_names"]

        # 7. Start
        start_result = start_adventure(payload)
        assert start_result["success"]
        assert start_result["session_id"]
        assert "cyberpunk" in start_result["world"]["genre"]

    def test_blank_setup_flow(self):
        """Start from blank, fill minimal fields, launch."""
        payload = _minimal_setup(setup_id="blank_test")
        result = start_adventure(payload)
        assert result["success"]
        assert result["opening"]

    def test_template_edit_then_launch(self):
        """Template → edit premise → launch."""
        tpl = build_template_payload("political_intrigue")
        payload = tpl["setup"]
        payload["setup_id"] = "edit_test"
        payload["title"] = "Custom Intrigue"
        payload["premise"] = "A completely new premise about power struggles in a distant kingdom"
        result = start_adventure(payload)
        assert result["success"]
        assert "political intrigue" in result["world"]["genre"]


# ===================================================================
# Patch 7 — Regression tests for contract keys and invalid payloads
# ===================================================================


class TestPreviewResponseContract:
    """Lock the preview response shape used by the frontend."""

    def test_preview_has_response_version(self):
        result = preview_setup(_minimal_setup())
        assert result.get("response_version") == ADVENTURE_PREVIEW_RESPONSE_VERSION

    def test_preview_has_required_keys(self):
        result = preview_setup(_minimal_setup())
        required_keys = {"success", "response_version", "ok", "validation", "preview", "resolved_context"}
        assert required_keys.issubset(result.keys())

    def test_preview_validation_shape(self):
        result = preview_setup(_minimal_setup())
        validation = result.get("validation", {})
        assert "issues" in validation
        assert "blocking" in validation

    def test_preview_counts_shape(self):
        result = preview_setup(_rich_setup())
        counts = result.get("preview", {}).get("counts", {})
        assert "factions" in counts
        assert "locations" in counts
        assert "npcs" in counts

    def test_preview_resolved_context_keys(self):
        result = preview_setup(_rich_setup())
        ctx = result.get("resolved_context", {})
        required_keys = {"location_id", "location_name", "npc_ids", "npc_names"}
        assert required_keys.issubset(ctx.keys())


class TestStartResponseContract:
    """Lock the start response shape used by the frontend."""

    def test_start_has_response_version(self):
        result = start_adventure(_minimal_setup())
        assert result.get("response_version") == ADVENTURE_START_RESPONSE_VERSION

    def test_start_has_required_keys(self):
        result = start_adventure(_minimal_setup())
        required_keys = {
            "success", "session_id", "opening", "world", "player",
            "npcs", "locations", "factions", "memory", "worldEvents",
            "creator",
        }
        assert required_keys.issubset(result.keys())

    def test_start_has_version_metadata(self):
        result = start_adventure(_minimal_setup())
        assert result.get("start_response_version") == ADVENTURE_START_RESPONSE_VERSION
        assert result.get("preview_response_version") == ADVENTURE_PREVIEW_RESPONSE_VERSION

    def test_start_creator_metadata(self):
        result = start_adventure(_minimal_setup())
        creator = result.get("creator", {})
        assert "setup_id" in creator


class TestAdapterHandlesPartialResult:
    """Ensure adapter handles None / partial internal output gracefully."""

    def test_handles_all_none(self):
        result = adapt_start_result({
            "generated": None,
            "setup": None,
            "canon_summary": None,
        })
        assert result["success"] is True
        assert result["npcs"] == []
        assert result["locations"] == []
        assert result["factions"] == []
        assert result["memory"] == []
        assert result["worldEvents"] == []

    def test_handles_string_values(self):
        """Non-list/non-dict values should be safely converted."""
        result = adapt_start_result({
            "generated": "broken",
            "setup": "broken",
            "canon_summary": "broken",
        })
        assert result["success"] is True
        assert result["world"]["title"] == ""
        assert result["player"]["name"] == "Player"

    def test_handles_missing_keys(self):
        result = adapt_start_result({})
        assert result["success"] is True
        assert result["session_id"]  # should generate UUID

    def test_handles_npc_list_with_non_dicts(self):
        result = adapt_start_result({
            "ok": True,
            "setup": {},
            "generated": {
                "seed_npcs": [None, "string", {"npc_id": "n1", "name": "Valid"}],
            },
            "canon_summary": {},
        })
        # Should filter out non-dict entries
        assert len(result["npcs"]) == 1
        assert result["npcs"][0]["name"] == "Valid"

    def test_response_version_is_set(self):
        result = adapt_start_result({})
        assert result.get("response_version") == ADVENTURE_START_RESPONSE_VERSION
