from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from app.rpg.survival_autocare_policy import (
    attach_survival_autocare_policy,
    choose_survival_autocare_action,
)
from app.rpg.survival_report_metrics import build_survival_report_metrics, render_survival_report_html

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
COMMAND_BRIDGE_JS = STATIC / "rpg" / "rpg-command-bridge.js"
SURVIVAL_JS = STATIC / "rpg" / "rpg-survival-inspector.js"
JS_E2E = ROOT / "tests" / "rpg" / "js" / "survival_ui_e2e_smoke.cjs"


def _simulation(*, hunger=10, thirst=10, fatigue=10, items=None, currency=None):
    return {
        "survival": {"hunger": hunger, "thirst": thirst, "fatigue": fatigue, "events": []},
        "player_state": {
            "currency": currency or {"silver": 1},
            "inventory": {
                "items": list(items or []),
                "equipment": {},
            },
        },
    }


def _payload(pressure, actions=None):
    return {
        "result": {
            "survival_pressure": pressure,
            "survival_action_context": {
                "suggested_actions": [
                    {"action_id": "survival:" + action.replace(" ", "_"), "action": action, "action_type": "survival"}
                    for action in (actions or [])
                ]
            },
        }
    }


def test_bundle_bo_ui_command_e2e_smoke_clicks_and_rerenders() -> None:
    node = shutil.which("node")
    if not node:
        assert JS_E2E.exists()
        return

    proc = subprocess.run(
        [node, str(JS_E2E), str(COMMAND_BRIDGE_JS), str(SURVIVAL_JS)],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload == {"ok": True, "submitted": ["drink water", "eat rations"]}


def test_bundle_bp_autocare_prefers_inventory_then_purchase_fallback() -> None:
    water_sim = _simulation(
        thirst=85,
        items=[{"name": "Water", "quantity": 1, "tags": ["water", "survival"]}],
    )
    decision = choose_survival_autocare_action(
        payload=_payload({"thirst": "critical", "hunger": "low", "fatigue": "low"}, ["drink water", "buy water"]),
        simulation_state=water_sim,
    )
    assert decision["ok"] is True
    assert decision["action"] == "drink water"
    assert decision["need"] == "thirst"
    assert decision["selection_source"] == "inventory"

    no_water_sim = _simulation(thirst=85, items=[], currency={"silver": 1})
    decision = choose_survival_autocare_action(
        payload=_payload({"thirst": "critical", "hunger": "low", "fatigue": "low"}, ["buy water"]),
        simulation_state=no_water_sim,
    )
    assert decision["ok"] is True
    assert decision["action"] == "buy water"
    assert decision["selection_source"] in {"context", "fallback"}


def test_bundle_bp_autocare_avoids_recently_blocked_actions_and_attaches_next_action() -> None:
    sim = _simulation(thirst=90, items=[], currency={"silver": 1})
    history = [
        {"survival_result": {"ok": False, "action_category": "survival", "action": "buy_water", "blocked_reason": "merchant_unavailable"}},
        {"survival_result": {"ok": False, "action_category": "survival", "action": "buy_water", "blocked_reason": "merchant_unavailable"}},
    ]
    payload = _payload({"thirst": "critical", "hunger": "low", "fatigue": "low"}, ["buy water", "fill waterskin"])
    decision = choose_survival_autocare_action(payload=payload, simulation_state=sim, recent_history=history)
    assert decision["ok"] is True
    assert decision["action"] == "fill waterskin"

    attached = attach_survival_autocare_policy(payload, sim, recent_history=[])
    assert attached["survival_autocare_policy"]["ok"] is True
    assert attached["next_actions"][0]["action_type"] == "survival"


def _gate_row(turn, *, pressure, needs, action=None, blocked=False, tick_results=None, suggested_survival=True):
    survival_result = {}
    if action:
        survival_result = {
            "ok": not blocked,
            "action_category": "survival",
            "action": action,
        }
        if blocked:
            survival_result["blocked_reason"] = "no_water_available"
    suggested = [{"action_id": "survival:drink_water", "action": "drink water", "action_type": "survival"}] if suggested_survival else []
    return {
        "turn": turn,
        "result": {
            "survival": needs,
            "survival_pressure": pressure,
            "survival_tick_result": tick_results[0] if tick_results else {},
            "survival_result": survival_result,
            "suggested_actions": suggested,
        },
        "turn_contract": {
            "survival": needs,
            "survival_pressure": pressure,
            "survival_tick_result": tick_results[1] if tick_results and len(tick_results) > 1 else {},
        },
    }


def test_bundle_bq_report_metrics_emit_advisory_gates_for_runaway_survival() -> None:
    rows = []
    for turn in range(1, 6):
        rows.append(_gate_row(
            turn,
            pressure={"hunger": "low", "thirst": "critical", "fatigue": "low"},
            needs={"hunger": 10, "thirst": 95, "fatigue": 10},
            action="drink_water",
            blocked=turn <= 3,
            tick_results=[
                {"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn}"},
                {"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn}:duplicate"},
            ] if turn == 4 else [{"applied": True, "reason": "standard_turn", "turn_id": f"turn:{turn}"}],
        ))

    metrics = build_survival_report_metrics(rows)
    gates = metrics["advisory_gates"]
    html = render_survival_report_html(metrics)

    assert gates["advisory_only"] is True
    assert gates["ok"] is False
    assert "critical_pressure_streak" in gates["failed"]
    assert "repeated_blocked_actions" in gates["failed"]
    assert "passive_tick_single_application" in gates["failed"]
    assert "survival_suggestion_dominance" in gates["failed"]
    assert metrics["summary"]["warning_counts"]["gate:critical_pressure_streak"] == 1
    assert "Advisory Survival Gates" in html
    assert "passive_tick_single_application" in html
    json.dumps(metrics)
