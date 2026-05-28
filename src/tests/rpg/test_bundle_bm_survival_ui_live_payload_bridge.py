from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
BRIDGE_JS = STATIC / "rpg" / "rpg-live-payload-bridge.js"
SETTINGS_JS = STATIC / "rpg-conversation-settings.js"
JS_HARNESS = ROOT / "tests" / "rpg" / "js" / "live_payload_bridge_smoke.cjs"


def test_bundle_bm_live_payload_bridge_exports_and_dispatches_expected_events() -> None:
    bridge = BRIDGE_JS.read_text(encoding="utf-8")

    assert "window.RpgLivePayloadBridge" in bridge
    assert "dispatchRpgPayload" in bridge
    assert "hasSurvivalEvidence" in bridge
    assert "rpg:turn_payload" in bridge
    assert "rpg:survival_payload" in bridge
    assert "/api/rpg" in bridge
    assert "response.clone().json().then" in bridge
    assert "rpg_live_payload_bridge" in bridge


def test_bundle_bm_settings_loader_loads_bridge_before_survival_inspector() -> None:
    settings = SETTINGS_JS.read_text(encoding="utf-8")

    assert "ensureLivePayloadBridgeScript" in settings
    assert "/static/rpg/rpg-live-payload-bridge.js" in settings
    assert "rpg-live-payload-bridge-script" in settings
    assert "ensureLivePayloadBridgeScript();\n    const script = document.createElement(\"script\");\n    script.id = \"rpg-survival-inspector-script\"" in settings
    assert "ensureLivePayloadBridgeScript," in settings


def test_bundle_bm_live_payload_bridge_node_smoke_dispatches_events() -> None:
    node = shutil.which("node")
    if not node:
        assert JS_HARNESS.exists()
        return

    proc = subprocess.run(
        [node, str(JS_HARNESS), str(BRIDGE_JS)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert "rpg:turn_payload" in payload["events"]
    assert "rpg:survival_payload" in payload["events"]
