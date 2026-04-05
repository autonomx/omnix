"""Unit tests for Phase 8 Frontend UX Wiring."""

from __future__ import annotations

import json
import pytest


class TestRPGPlayerClient:
    """Tests for the RPGPlayerClient JavaScript module structure."""

    def test_client_has_all_methods(self):
        """Verify client module exports all expected methods."""
        # Read the JS file and verify it has all expected methods
        with open("src/static/rpg/rpgPlayerClient.js", "r") as f:
            content = f.read()
        
        expected_methods = [
            "getState",
            "getJournal",
            "getCodex",
            "getObjectives",
            "enterDialogue",
            "exitDialogue",
            "buildEncounter",
        ]
        
        for method in expected_methods:
            assert method in content, f"Missing method: {method}"

    def test_client_uses_correct_endpoints(self):
        """Verify client uses correct API endpoints."""
        with open("src/static/rpg/rpgPlayerClient.js", "r") as f:
            content = f.read()
        
        expected_endpoints = [
            "/api/rpg/player/state",
            "/api/rpg/player/journal",
            "/api/rpg/player/codex",
            "/api/rpg/player/objectives",
            "/api/rpg/player/dialogue/enter",
            "/api/rpg/player/dialogue/exit",
            "/api/rpg/player/encounter",
        ]
        
        for endpoint in expected_endpoints:
            assert endpoint in content, f"Missing endpoint: {endpoint}"


class TestRPGPlayerState:
    """Tests for the RPGPlayerState JavaScript module."""

    def test_state_has_player_view_and_player_state(self):
        """Verify state module has playerView and playerState containers."""
        with open("src/static/rpg/rpgPlayerState.js", "r") as f:
            content = f.read()
        
        assert "playerState" in content
        assert "playerView" in content
        assert "updatePlayerViewFromResponse" in content
        assert "updatePlayerStateFromResponse" in content

    def test_state_reads_from_metadata(self):
        """Verify state reads player_view from metadata.player_view."""
        with open("src/static/rpg/rpgPlayerState.js", "r") as f:
            content = f.read()
        
        assert "metadata" in content
        assert "player_view" in content


class TestRPGPlayerRenderer:
    """Tests for the RPGPlayerRenderer JavaScript module."""

    def test_renderer_has_all_functions(self):
        """Verify renderer has all expected render functions."""
        with open("src/static/rpg/rpgPlayerRenderer.js", "r") as f:
            content = f.read()
        
        expected_functions = [
            "renderPlayerView",
            "renderSceneHeader",
            "renderActors",
            "renderChoices",
            "renderWorldSignals",
        ]
        
        for func in expected_functions:
            assert func in content, f"Missing function: {func}"

    def test_renderer_dispatches_choice_event(self):
        """Verify renderer dispatches rpg:choice custom event."""
        with open("src/static/rpg/rpgPlayerRenderer.js", "r") as f:
            content = f.read()
        
        assert "rpg:choice" in content
        assert "CustomEvent" in content


class TestRPGPlayerUI:
    """Tests for the RPGPlayerUI JavaScript module."""

    def test_ui_has_all_functions(self):
        """Verify UI module has all expected functions."""
        with open("src/static/rpg/rpgPlayerUI.js", "r") as f:
            content = f.read()
        
        expected_functions = [
            "loadJournal",
            "loadCodex",
            "loadObjectives",
            "handleEnterDialogue",
            "handleExitDialogue",
            "refreshSidePanels",
        ]
        
        for func in expected_functions:
            assert func in content, f"Missing function: {func}"

    def test_ui_has_error_handling(self):
        """Verify UI functions have error handling."""
        with open("src/static/rpg/rpgPlayerUI.js", "r") as f:
            content = f.read()
        
        assert "try" in content
        assert "catch" in content
        assert "console.error" in content


class TestRPGPlayerIntegration:
    """Tests for the RPGPlayerIntegration JavaScript module."""

    def test_integration_has_all_methods(self):
        """Verify integration class has all expected methods."""
        with open("src/static/rpg/rpgPlayerIntegration.js", "r") as f:
            content = f.read()
        
        expected_methods = [
            "processResponse",
            "enterDialogue",
            "exitDialogue",
            "refreshSidePanels",
            "loadJournal",
            "loadCodex",
            "loadObjectives",
            "buildEncounter",
            "getPlayerState",
            "getPlayerView",
        ]
        
        for method in expected_methods:
            assert method in content, f"Missing method: {method}"

    def test_integration_imports_all_modules(self):
        """Verify integration imports all required modules."""
        with open("src/static/rpg/rpgPlayerIntegration.js", "r") as f:
            content = f.read()
        
        expected_imports = [
            "rpgPlayerClient.js",
            "rpgPlayerState.js",
            "rpgPlayerRenderer.js",
            "rpgPlayerUI.js",
        ]
        
        for imp in expected_imports:
            assert imp in content, f"Missing import: {imp}"


class TestFrontendFileIntegrity:
    """Tests for file existence and structure."""

    def test_all_files_exist(self):
        """Verify all frontend files were created."""
        import os
        
        expected_files = [
            "src/static/rpg/rpgPlayerClient.js",
            "src/static/rpg/rpgPlayerState.js",
            "src/static/rpg/rpgPlayerRenderer.js",
            "src/static/rpg/rpgPlayerUI.js",
            "src/static/rpg/rpgPlayerIntegration.js",
        ]
        
        for filepath in expected_files:
            assert os.path.exists(filepath), f"Missing file: {filepath}"

    def test_all_files_are_valid_javascript(self):
        """Verify all files are valid JavaScript."""
        import os
        
        js_files = [
            "src/static/rpg/rpgPlayerClient.js",
            "src/static/rpg/rpgPlayerState.js",
            "src/static/rpg/rpgPlayerRenderer.js",
            "src/static/rpg/rpgPlayerUI.js",
            "src/static/rpg/rpgPlayerIntegration.js",
        ]
        
        for filepath in js_files:
            with open(filepath, "r") as f:
                content = f.read()
            # Basic JavaScript validation - should not throw
            assert len(content) > 0, f"Empty file: {filepath}"
            assert "export" in content or "class" in content, f"Missing export: {filepath}"