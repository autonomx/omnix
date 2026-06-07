from tests.rpg.autoplay.live_manual_turn_timing import (
    classify_stage_name,
    should_wrap_timing_function,
    wrap_live_manual_turn_timing_functions,
)


def test_phase13_22_timing_wrapper_ignores_scan_helpers():
    assert classify_stage_name("_scan_for_grounding_validation") is None
    assert classify_stage_name("_extract_grounding_validation_from_any") is None

    def _scan_for_grounding_validation(payload):
        total = 0
        for value in payload.get("values", range(12)):
            total += int(value)
        return {"elapsed_ms": total}

    def _extract_grounding_validation_from_any(payload):
        total = 0
        for value in payload.get("values", range(12)):
            total += int(value)
        return {"elapsed_ms": total}

    namespace = {
        "_scan_for_grounding_validation": _scan_for_grounding_validation,
        "_extract_grounding_validation_from_any": _extract_grounding_validation_from_any,
    }
    result = wrap_live_manual_turn_timing_functions(namespace)
    assert result["wrapped_count"] == 0
    assert namespace["_scan_for_grounding_validation"] is _scan_for_grounding_validation
    assert namespace["_extract_grounding_validation_from_any"] is _extract_grounding_validation_from_any
    assert not should_wrap_timing_function("_scan_for_grounding_validation", _scan_for_grounding_validation)
    assert not should_wrap_timing_function("_extract_grounding_validation_from_any", _extract_grounding_validation_from_any)


def test_phase13_22_timing_wrapper_ignores_report_modules():
    def collect_grounding_validation_timing(payload):
        total = 0
        for value in payload.get("values", range(12)):
            total += int(value)
        return {"elapsed_ms": total}

    collect_grounding_validation_timing.__module__ = "tests.rpg.autoplay.live_performance_bridge"
    assert classify_stage_name("collect_grounding_validation_timing") is None
    assert not should_wrap_timing_function("collect_grounding_validation_timing", collect_grounding_validation_timing)
