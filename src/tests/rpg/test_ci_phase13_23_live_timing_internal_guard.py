from tests.rpg.autoplay.live_manual_turn_timing import classify_stage_name, should_wrap_timing_function


def test_phase13_23_timing_wrapper_ignores_private_bundle_helper_name():
    helper_name = "_" + "bundle_ai_" + "repair_" + "static_actions"
    assert classify_stage_name(helper_name) is None

    def helper(payload):
        total = 0
        for value in payload.get("values", range(12)):
            total += int(value)
        return {"elapsed_ms": total}

    assert not should_wrap_timing_function(helper_name, helper)


def test_phase13_23_timing_wrapper_keeps_public_stage_helper_name():
    def repair_intent_payload(payload):
        total = 0
        for value in payload.get("values", range(12)):
            total += int(value)
        return {"elapsed_ms": total}

    assert classify_stage_name("repair_intent_payload") == "repair_ms"
    assert should_wrap_timing_function("repair_intent_payload", repair_intent_payload)
