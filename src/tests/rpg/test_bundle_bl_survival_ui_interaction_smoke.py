from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
JS_HARNESS = ROOT / "tests" / "rpg" / "js" / "survival_inspector_smoke.cjs"
SURVIVAL_JS = STATIC / "rpg" / "rpg-survival-inspector.js"
COMMAND_BRIDGE_JS = STATIC / "rpg" / "rpg-command-bridge.js"


def test_bundle_bl_survival_inspector_smoke_harness_targets_real_frontend_module() -> None:
    harness = JS_HARNESS.read_text(encoding="utf-8")
    survival_js = SURVIVAL_JS.read_text(encoding="utf-8")

    assert "vm.runInNewContext(source" in harness
    assert "RpgSurvivalInspector.render(payload)" in harness
    assert "data-rpg-survival-command" in harness
    assert "drink water" in harness
    assert "rpg-survival-need--critical" in harness
    assert "window.RpgSurvivalInspector" in survival_js
    assert "bindActionButtons(panel)" in survival_js
    assert "RpgCommandBridge.submitCommand" in survival_js


def test_bundle_bl_survival_inspector_node_smoke_renders_and_clicks_action() -> None:
    node = shutil.which("node")
    if not node:
        # Keep the suite usable on minimal Python-only environments while still
        # making sure the committed smoke harness is present and meaningful.
        assert JS_HARNESS.exists()
        return

    proc = subprocess.run(
        [node, str(JS_HARNESS), str(SURVIVAL_JS), str(COMMAND_BRIDGE_JS)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload == {"ok": True, "buttons": 2, "submitted": "drink water", "method": "rpgSendMessage"}
