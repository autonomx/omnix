def test_ci_runtime_wrapper_manifest_tracks_contract_chain():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()

    assert manifest["part_modules"][-5:] == [
        "runtime_part22",
        "runtime_part23",
        "runtime_part24",
        "runtime_part25",
        "runtime_part26",
    ]
    assert manifest["final_apply_turn_authoritative_module"] == "app.rpg.session.runtime_part26"
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
