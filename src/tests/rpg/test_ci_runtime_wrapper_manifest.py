import json


def test_ci_runtime_wrapper_manifest_tracks_contract_chain():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["part_modules"][-6:] == [
        "runtime_part22",
        "runtime_part23",
        "runtime_part24",
        "runtime_part25",
        "runtime_part26",
        "runtime_part27",
    ]
    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part27"
    assert manifest["final_apply_attack_combat_action_module"] == "app.rpg.session.runtime_part23"
    assert manifest["combat_contract_modules"] == [
        "app.rpg.session.runtime_part22",
        "app.rpg.session.runtime_part23",
        "app.rpg.session.runtime_part24",
        "app.rpg.session.runtime_part25",
        "app.rpg.session.runtime_part26",
    ]
    assert runtime._apply_turn_authoritative.__module__ == manifest["final_apply_turn_authoritative_module"]
    assert runtime._apply_attack_combat_action.__module__ == manifest["final_apply_attack_combat_action_module"]


def test_ci_runtime_wrapper_drift_report_is_clean_and_json_safe():
    from app.rpg.session import runtime

    report = runtime.get_runtime_wrapper_drift_report()

    assert report["ok"] is True
    assert report["missing_combat_contract_modules"] == []
    assert report["unexpected_combat_contract_modules"] == []
    assert report["actual_combat_contract_modules"] == report[
        "expected_combat_contract_modules"
    ]
    assert report["final_apply_turn_authoritative_module"] == report[
        "expected_final_apply_turn_authoritative_module"
    ]
    assert report["final_apply_attack_combat_action_module"] == report[
        "expected_final_apply_attack_combat_action_module"
    ]
    assert json.loads(json.dumps(report)) == report


def test_ci_campaign_report_displays_runtime_wrapper_manifest():
    from tests.rpg.autoplay.campaign_report import render_campaign_report_html

    html = render_campaign_report_html({"scenario_seed": "ci_runtime_manifest_report"})

    assert "Runtime Wrapper Manifest" in html
    assert "Runtime wrapper drift status" in html
    assert "<strong>clean</strong>" in html
    assert "Expected wrappers" in html
    assert "Actual wrappers" in html
    assert "Missing wrappers" in html
    assert "Unexpected wrappers" in html
    assert "app.rpg.session.runtime_part22" in html
    assert "app.rpg.session.runtime_part26" in html
    assert "app.rpg.session.runtime_part27" in html
    assert "app.rpg.session.runtime_part23" in html
