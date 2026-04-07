"""RPG API Healthcheck Tests.

Tests that all RPG API endpoints are registered and respond correctly
(i.e., not 404 Not Found). This ensures route registration is complete
and the server can handle requests across all RPG modules.

Uses setup_method pattern like other functional tests in this project.
"""
from __future__ import annotations

from app import create_app


class TestRPGAdventureAPIHealthcheck:
    """Healthcheck tests for /api/rpg/adventure/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_get_adventure_templates(self):
        resp = self.client.get("/api/rpg/adventure/templates")
        assert resp.status_code != 404, "Adventure templates endpoint not found"

    def test_post_adventure_validate(self):
        resp = self.client.post("/api/rpg/adventure/validate", json={"setup": {}})
        assert resp.status_code != 404, "Adventure validate endpoint not found"

    def test_post_adventure_preview(self):
        resp = self.client.post("/api/rpg/adventure/preview", json={"setup": {}})
        assert resp.status_code != 404, "Adventure preview endpoint not found"

    def test_post_adventure_start(self):
        resp = self.client.post("/api/rpg/adventure/start", json={"setup": {}})
        assert resp.status_code != 404, "Adventure start endpoint not found"

    def test_post_adventure_regenerate(self):
        resp = self.client.post("/api/rpg/adventure/regenerate", json={"setup": {}, "target": "locations"})
        assert resp.status_code != 404, "Adventure regenerate endpoint not found"

    def test_post_adventure_regenerate_item(self):
        resp = self.client.post("/api/rpg/adventure/regenerate-item", json={"setup": {}, "target": "locations", "item_id": "loc_1"})
        assert resp.status_code != 404, "Adventure regenerate-item endpoint not found"

    def test_post_adventure_regenerate_multiple(self):
        resp = self.client.post("/api/rpg/adventure/regenerate-multiple", json={"setup": {}, "target": "locations", "item_ids": ["loc_1"]})
        assert resp.status_code != 404, "Adventure regenerate-multiple endpoint not found"

    def test_post_adventure_inspect_world(self):
        resp = self.client.post("/api/rpg/adventure/inspect-world", json={"setup": {}})
        assert resp.status_code != 404, "Adventure inspect-world endpoint not found"

    def test_post_adventure_inspect_world_snapshot(self):
        resp = self.client.post("/api/rpg/adventure/inspect-world-snapshot", json={"setup": {}})
        assert resp.status_code != 404, "Adventure inspect-world-snapshot endpoint not found"

    def test_post_adventure_compare_world(self):
        resp = self.client.post("/api/rpg/adventure/compare-world", json={"before_setup": {}, "after_setup": {}})
        assert resp.status_code != 404, "Adventure compare-world endpoint not found"

    def test_post_adventure_compare_entity(self):
        resp = self.client.post("/api/rpg/adventure/compare-entity", json={"before_setup": {}, "after_setup": {}, "entity_id": "test"})
        assert resp.status_code != 404, "Adventure compare-entity endpoint not found"

    def test_post_adventure_simulate_step(self):
        resp = self.client.post("/api/rpg/adventure/simulate-step", json={"setup": {}})
        assert resp.status_code != 404, "Adventure simulate-step endpoint not found"

    def test_post_adventure_simulation_state(self):
        resp = self.client.post("/api/rpg/adventure/simulation-state", json={"setup": {}})
        assert resp.status_code != 404, "Adventure simulation-state endpoint not found"


class TestRPGDialogueAPIHealthcheck:
    """Healthcheck tests for /api/rpg/dialogue/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_dialogue_start(self):
        resp = self.client.post("/api/rpg/dialogue/start", json={})
        assert resp.status_code != 404, "Dialogue start endpoint not found"

    def test_post_dialogue_message(self):
        resp = self.client.post("/api/rpg/dialogue/message", json={})
        assert resp.status_code != 404, "Dialogue message endpoint not found"

    def test_post_dialogue_end(self):
        resp = self.client.post("/api/rpg/dialogue/end", json={})
        assert resp.status_code != 404, "Dialogue end endpoint not found"


class TestRPGEncounterAPIHealthcheck:
    """Healthcheck tests for /api/rpg/encounter/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_encounter_start(self):
        resp = self.client.post("/api/rpg/encounter/start", json={})
        assert resp.status_code != 404, "Encounter start endpoint not found"

    def test_post_encounter_action(self):
        resp = self.client.post("/api/rpg/encounter/action", json={})
        assert resp.status_code != 404, "Encounter action endpoint not found"

    def test_post_encounter_npc_turn(self):
        resp = self.client.post("/api/rpg/encounter/npc_turn", json={})
        assert resp.status_code != 404, "Encounter npc_turn endpoint not found"

    def test_post_encounter_end(self):
        resp = self.client.post("/api/rpg/encounter/end", json={})
        assert resp.status_code != 404, "Encounter end endpoint not found"


class TestRPGPlayerAPIHealthcheck:
    """Healthcheck tests for /api/rpg/player/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_player_state(self):
        resp = self.client.post("/api/rpg/player/state", json={})
        assert resp.status_code != 404, "Player state endpoint not found"

    def test_post_player_journal(self):
        resp = self.client.post("/api/rpg/player/journal", json={})
        assert resp.status_code != 404, "Player journal endpoint not found"

    def test_post_player_codex(self):
        resp = self.client.post("/api/rpg/player/codex", json={})
        assert resp.status_code != 404, "Player codex endpoint not found"

    def test_post_player_objectives(self):
        resp = self.client.post("/api/rpg/player/objectives", json={})
        assert resp.status_code != 404, "Player objectives endpoint not found"

    def test_post_player_dialogue_enter(self):
        resp = self.client.post("/api/rpg/player/dialogue/enter", json={})
        assert resp.status_code != 404, "Player dialogue enter endpoint not found"

    def test_post_player_dialogue_exit(self):
        resp = self.client.post("/api/rpg/player/dialogue/exit", json={})
        assert resp.status_code != 404, "Player dialogue exit endpoint not found"

    def test_post_player_encounter(self):
        resp = self.client.post("/api/rpg/player/encounter", json={})
        assert resp.status_code != 404, "Player encounter endpoint not found"

    def test_post_player_inventory(self):
        resp = self.client.post("/api/rpg/player/inventory", json={})
        assert resp.status_code != 404, "Player inventory endpoint not found"

    def test_post_player_inventory_use(self):
        resp = self.client.post("/api/rpg/player/inventory/use", json={})
        assert resp.status_code != 404, "Player inventory use endpoint not found"

    def test_post_player_inventory_registry(self):
        resp = self.client.post("/api/rpg/player/inventory/registry", json={})
        assert resp.status_code != 404, "Player inventory registry endpoint not found"

    def test_post_player_party(self):
        resp = self.client.post("/api/rpg/player/party", json={})
        assert resp.status_code != 404, "Player party endpoint not found"

    def test_post_player_party_recruit(self):
        resp = self.client.post("/api/rpg/player/party/recruit", json={})
        assert resp.status_code != 404, "Player party recruit endpoint not found"

    def test_post_player_party_remove(self):
        resp = self.client.post("/api/rpg/player/party/remove", json={})
        assert resp.status_code != 404, "Player party remove endpoint not found"


class TestRPGInspectionAPIHealthcheck:
    """Healthcheck tests for /api/rpg/inspect/* and /api/rpg/gm/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_inspect_timeline(self):
        resp = self.client.post("/api/rpg/inspect/timeline", json={})
        assert resp.status_code != 404, "Inspect timeline endpoint not found"

    def test_post_inspect_timeline_tick(self):
        resp = self.client.post("/api/rpg/inspect/timeline_tick", json={})
        assert resp.status_code != 404, "Inspect timeline tick endpoint not found"

    def test_post_inspect_tick_diff(self):
        resp = self.client.post("/api/rpg/inspect/tick_diff", json={})
        assert resp.status_code != 404, "Inspect tick diff endpoint not found"

    def test_post_inspect_npc_reasoning(self):
        resp = self.client.post("/api/rpg/inspect/npc_reasoning", json={})
        assert resp.status_code != 404, "Inspect npc reasoning endpoint not found"

    def test_post_gm_force_npc_goal(self):
        resp = self.client.post("/api/rpg/gm/force_npc_goal", json={})
        assert resp.status_code != 404, "GM force npc goal endpoint not found"

    def test_post_gm_force_faction_trend(self):
        resp = self.client.post("/api/rpg/gm/force_faction_trend", json={})
        assert resp.status_code != 404, "GM force faction trend endpoint not found"

    def test_post_gm_debug_note(self):
        resp = self.client.post("/api/rpg/gm/debug_note", json={})
        assert resp.status_code != 404, "GM debug note endpoint not found"


class TestRPGDebugAPIHealthcheck:
    """Healthcheck tests for /api/rpg/debug/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_debug_state(self):
        resp = self.client.post("/api/rpg/debug/state", json={})
        assert resp.status_code != 404, "Debug state endpoint not found"

    def test_post_debug_npc(self):
        resp = self.client.post("/api/rpg/debug/npc", json={})
        assert resp.status_code != 404, "Debug npc endpoint not found"

    def test_post_debug_faction(self):
        resp = self.client.post("/api/rpg/debug/faction", json={})
        assert resp.status_code != 404, "Debug faction endpoint not found"

    def test_post_debug_step(self):
        resp = self.client.post("/api/rpg/debug/step", json={})
        assert resp.status_code != 404, "Debug step endpoint not found"

    def test_post_debug_inject_event(self):
        resp = self.client.post("/api/rpg/debug/inject_event", json={})
        assert resp.status_code != 404, "Debug inject event endpoint not found"

    def test_post_debug_seed_rumor(self):
        resp = self.client.post("/api/rpg/debug/seed_rumor", json={})
        assert resp.status_code != 404, "Debug seed rumor endpoint not found"

    def test_post_debug_force_alliance(self):
        resp = self.client.post("/api/rpg/debug/force_alliance", json={})
        assert resp.status_code != 404, "Debug force alliance endpoint not found"

    def test_post_debug_force_faction_position(self):
        resp = self.client.post("/api/rpg/debug/force_faction_position", json={})
        assert resp.status_code != 404, "Debug force faction position endpoint not found"

    def test_post_debug_force_npc_belief(self):
        resp = self.client.post("/api/rpg/debug/force_npc_belief", json={})
        assert resp.status_code != 404, "Debug force npc belief endpoint not found"

    def test_post_debug_snapshots(self):
        resp = self.client.post("/api/rpg/debug/snapshots", json={})
        assert resp.status_code != 404, "Debug snapshots endpoint not found"

    def test_post_debug_snapshot(self):
        resp = self.client.post("/api/rpg/debug/snapshot", json={})
        assert resp.status_code != 404, "Debug snapshot endpoint not found"

    def test_post_debug_rollback(self):
        resp = self.client.post("/api/rpg/debug/rollback", json={})
        assert resp.status_code != 404, "Debug rollback endpoint not found"


class TestRPGPresentationAPIHealthcheck:
    """Healthcheck tests for /api/rpg/presentation/* and related endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_presentation_scene(self):
        resp = self.client.post("/api/rpg/presentation/scene", json={})
        assert resp.status_code != 404, "Presentation scene endpoint not found"

    def test_post_presentation_dialogue(self):
        resp = self.client.post("/api/rpg/presentation/dialogue", json={})
        assert resp.status_code != 404, "Presentation dialogue endpoint not found"

    def test_post_presentation_speakers(self):
        resp = self.client.post("/api/rpg/presentation/speakers", json={})
        assert resp.status_code != 404, "Presentation speakers endpoint not found"

    def test_post_setup_flow(self):
        resp = self.client.post("/setup-flow", json={})
        assert resp.status_code != 404, "Setup flow endpoint not found"

    def test_post_session_bootstrap(self):
        resp = self.client.post("/session-bootstrap", json={})
        assert resp.status_code != 404, "Session bootstrap endpoint not found"

    def test_post_intro_scene(self):
        resp = self.client.post("/intro-scene", json={})
        assert resp.status_code != 404, "Intro scene endpoint not found"

    def test_post_save_load_ux(self):
        resp = self.client.post("/save-load-ux", json={})
        assert resp.status_code != 404, "Save load UX endpoint not found"

    def test_post_narrative_recap(self):
        resp = self.client.post("/narrative-recap", json={})
        assert resp.status_code != 404, "Narrative recap endpoint not found"

    def test_post_character_ui(self):
        resp = self.client.post("/api/rpg/character_ui", json={})
        assert resp.status_code != 404, "Character UI endpoint not found"

    def test_post_character_inspector(self):
        resp = self.client.post("/api/rpg/character_inspector", json={})
        assert resp.status_code != 404, "Character inspector endpoint not found"

    def test_post_character_inspector_detail(self):
        resp = self.client.post("/api/rpg/character_inspector/detail", json={})
        assert resp.status_code != 404, "Character inspector detail endpoint not found"

    def test_post_world_inspector(self):
        resp = self.client.post("/api/rpg/world_inspector", json={})
        assert resp.status_code != 404, "World inspector endpoint not found"

    def test_post_character_portrait_request(self):
        resp = self.client.post("/api/rpg/character_portrait/request", json={})
        assert resp.status_code != 404, "Character portrait request endpoint not found"

    def test_post_character_portrait_result(self):
        resp = self.client.post("/api/rpg/character_portrait/result", json={})
        assert resp.status_code != 404, "Character portrait result endpoint not found"


class TestRPGPackageAPIHealthcheck:
    """Healthcheck tests for /api/rpg/package/* endpoints."""

    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_post_package_export(self):
        resp = self.client.post("/api/rpg/package/export", json={})
        assert resp.status_code != 404, "Package export endpoint not found"

    def test_post_package_import(self):
        resp = self.client.post("/api/rpg/package/import", json={})
        assert resp.status_code != 404, "Package import endpoint not found"

    def test_post_package_validate(self):
        resp = self.client.post("/api/rpg/package/validate", json={})
        assert resp.status_code != 404, "Package validate endpoint not found"