from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
COMMAND_BRIDGE_JS = STATIC / "rpg" / "rpg-command-bridge.js"
SURVIVAL_JS = STATIC / "rpg" / "rpg-survival-inspector.js"
SETTINGS_JS = STATIC / "rpg-conversation-settings.js"
JS_HARNESS = ROOT / "tests" / "rpg" / "js" / "command_bridge_smoke.cjs"


def test_bundle_bn_command_bridge_static_exports_and_event_contract() -> None:
    js = COMMAND_BRIDGE_JS.read_text(encoding="utf-8")

    assert "window.RpgCommandBridge" in js
    assert "submitCommand" in js
    assert "dispatchSubmitCommandEvent" in js
    assert "fallbackToInput" in js
    assert "rpg:submit_command" in js
    assert "cancelable: true" in js
    assert "rpgSendMessage" in js
    assert "sendRpgMessage" in js
    assert "RpgClient.sendCommand" in js
    assert "textarea, input[type='text']" in js


def test_bundle_bn_survival_inspector_uses_command_bridge_and_records_submit_result() -> None:
    js = SURVIVAL_JS.read_text(encoding="utf-8")

    assert "window.RpgCommandBridge.submitCommand" in js
    assert "rpg:submit_command" in js
    assert "button.dataset.submitMethod" in js
    assert "button.dataset.submitHandled" in js
    assert "action_type: \"survival\"" in js
    assert "submitSurvivalCommand" in js


def test_bundle_bn_settings_loads_command_bridge_before_live_payload_and_survival_inspector() -> None:
    js = SETTINGS_JS.read_text(encoding="utf-8")

    assert "ensureCommandBridgeScript" in js
    assert "/static/rpg/rpg-command-bridge.js" in js
    assert "rpg-command-bridge-script" in js
    assert "ensureCommandBridgeScript();\n    ensureLivePayloadBridgeScript();\n    const script = document.createElement(\"script\");\n    script.id = \"rpg-survival-inspector-script\"" in js
    assert "ensureCommandBridgeScript," in js


def test_bundle_bn_command_bridge_node_smoke_covers_direct_event_and_input_paths() -> None:
    node = shutil.which("node")
    if not node:
        assert JS_HARNESS.exists()
        return

    proc = subprocess.run(
        [node, str(JS_HARNESS), str(COMMAND_BRIDGE_JS)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload == {"ok": True, "direct": "drink water", "event": "rest", "input": "buy water"}
