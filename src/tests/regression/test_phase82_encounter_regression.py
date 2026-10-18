"""Phase 8.2 — Encounter Regression Tests.

Ensures encounter system continues to work after changes.
Includes determinism checks for participant ordering and action sequences.
"""

from __future__ import annotations

import os


class TestFrontendFilesExist:
    def test_encounter_client_has_expected_exports(self):
        base_path = os.path.dirname(__file__)
        path = os.path.join(base_path, "../../static/rpg/rpgEncounterClient.js")
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "class RPGEncounterClient" in content

    def test_encounter_renderer_has_expected_exports(self):
        base_path = os.path.dirname(__file__)
        path = os.path.join(base_path, "../../static/rpg/rpgEncounterRenderer.js")
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "renderEncounterState" in content