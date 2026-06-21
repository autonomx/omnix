import json
import linecache
from pathlib import Path

from app.rpg.autoplay_performance_artifacts import build_autoplay_performance_summary
from tests.rpg.autoplay.live_manual_turn_timing import (
    ARTIFACT_NAME as LIVE_TIMING_ARTIFACT_NAME,
    classify_stage_name,
    configure_live_manual_turn_timing,
    record_substage_timing,
    should_wrap_timing_function,
    wrap_live_manual_turn_timing_functions,
)
from tests.rpg.autoplay.live_performance_bridge import append_live_performance_bridge_row
from tests.rpg.autoplay.probe_source_map import (
    ARTIFACT_NAME as PROBE_SOURCE_MAP_NAME,
    EVENT_TEXT,
    build_probe_source_map_from_source,
    configure_probe_source_map,
    write_probe_source_map_from_linecache,
)
from tests.rpg.autoplay.survival_report_writer_hook import (
    load_live_manual_timing_rows,
    run_autoplay_survival_report_writer_hook,
)


def test_phase13_20_classifies_requested_substage_names():
    assert classify_stage_name("call_pre_runtime_intent_llm") == "pre_runtime_intent_llm_ms"
    assert classify_stage_name("deterministic_runtime_apply_state") == "deterministic_runtime_apply_ms"
    assert classify_stage_name("run_grounding_validator") == "grounding_validation_ms"
    assert classify_stage_name("repair_intent_payload") == "repair_ms"
    assert classify_stage_name("_run_real_autoplay") is None
    assert classify_stage_name("runtime_facade_manifest_gate") is None


def test_phase13_20_records_substage_timing_artifact(tmp_path: Path):
    configure_live_manual_turn_timing(output_dir=tmp_path)
    record_substage_timing("pre_runtime_intent_llm_ms", "call_pre_runtime_intent_llm", 12.5, turn_index=3)
    payload = json.loads((tmp_path / LIVE_TIMING_ARTIFACT_NAME).read_text(encoding="utf-8"))
    assert payload["event_count"] == 1
    assert payload["events"][0]["turn_index"] == 3
    assert payload["stage_summary"]["pre_runtime_intent_llm_ms"]["avg_ms"] == 12.5


def test_phase13_20_timing_wrapper_does_not_wrap_runner_or_manifest():
    def call_pre_runtime_intent_llm(payload):
        total = 0
        for index, value in enumerate(payload.get("values", [1, 2, 3, 4])):
            total += index + int(value)
        payload = dict(payload)
        payload["total"] = total
        payload["stage"] = "intent"
        return payload

    def _run_real_autoplay():
        return "real"

    def runtime_facade_manifest_gate():
        return True

    namespace = {
        "call_pre_runtime_intent_llm": call_pre_runtime_intent_llm,
        "_run_real_autoplay": _run_real_autoplay,
        "runtime_facade_manifest_gate": runtime_facade_manifest_gate,
    }
    result = wrap_live_manual_turn_timing_functions(namespace)
    assert result["wrapped_count"] == 1
    assert namespace["_run_real_autoplay"] is _run_real_autoplay
    assert namespace["runtime_facade_manifest_gate"] is runtime_facade_manifest_gate
    assert not should_wrap_timing_function("_run_real_autoplay", _run_real_autoplay)
    assert not should_wrap_timing_function("runtime_facade_manifest_gate", runtime_facade_manifest_gate)


def test_phase13_20_timing_wrapper_does_not_mutate_turn_runtime_calls():
    def _call_turn_runtime(**kwargs):
        return kwargs

    namespace = {"_call_turn_runtime": _call_turn_runtime}
    result = wrap_live_manual_turn_timing_functions(namespace)

    assert namespace["_call_turn_runtime"] is _call_turn_runtime
    assert "turn_call_context_wrapped" not in result


def test_phase13_20_live_timing_rows_bridge_missing_fields(tmp_path: Path):
    configure_live_manual_turn_timing(output_dir=tmp_path)
    record_substage_timing("pre_runtime_intent_llm_ms", "call_pre_runtime_intent_llm", 10.0, turn_index=1)
    record_substage_timing("deterministic_runtime_apply_ms", "deterministic_runtime_apply_state", 2.0, turn_index=1)
    record_substage_timing("grounding_validation_ms", "run_grounding_validator", 3.0, turn_index=1)
    record_substage_timing("repair_ms", "repair_intent_payload", 4.0, turn_index=1)
    rows = load_live_manual_timing_rows(tmp_path)
    bridged = append_live_performance_bridge_row(rows, {})
    summary = build_autoplay_performance_summary(bridged)
    breakdown = summary["manual_turn_breakdown"]["summary"]
    assert breakdown["pre_runtime_intent_llm_ms"]["avg_ms"] == 10.0
    assert breakdown["deterministic_runtime_apply_ms"]["avg_ms"] == 2.0
    assert breakdown["grounding_validation_ms"]["avg_ms"] == 3.0
    assert breakdown["repair_ms"]["avg_ms"] == 4.0


def test_phase13_20_builds_probe_source_map_from_generated_source():
    source = f"def helper():\n    result = {{'ok': False}}\n    emit_probe(event='{EVENT_TEXT}', result=result, turn_index=5)\n"
    payload = build_probe_source_map_from_source(source, filename="combined.py")
    assert payload["match_count"] == 1
    match = payload["matches"][0]
    assert match["enclosing_function_name"] == "helper"
    assert match["line_number"] == 3
    assert "emit_probe" in match["called_helper_names"]
    assert "turn_index" in match["referenced_local_names"]


def test_phase13_20_writes_probe_source_map_from_linecache(tmp_path: Path):
    configure_probe_source_map(output_dir=tmp_path)
    filename = "src/tests/rpg/autoplay_llm_campaign_parts/__combined_autoplay_llm_campaign__.py"
    source = f"def helper():\n    emit_probe(event='{EVENT_TEXT}', turn_index=5)\n"
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    result = write_probe_source_map_from_linecache()
    assert result["match_count"] == 1
    assert (tmp_path / PROBE_SOURCE_MAP_NAME).exists()


def test_phase13_20_post_run_hook_surfaces_timing_and_source_map(tmp_path: Path):
    configure_live_manual_turn_timing(output_dir=tmp_path)
    configure_probe_source_map(output_dir=tmp_path)
    record_substage_timing("pre_runtime_intent_llm_ms", "call_pre_runtime_intent_llm", 10.0, turn_index=1)
    filename = "src/tests/rpg/autoplay_llm_campaign_parts/__combined_autoplay_llm_campaign__.py"
    source = f"def helper():\n    emit_probe(event='{EVENT_TEXT}', turn_index=5)\n"
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    result = run_autoplay_survival_report_writer_hook(
        script_path=Path("src/tests/rpg/autoplay_llm_campaign.py"),
        results_dir=tmp_path,
    )
    assert result["ok"] is True
    assert result["live_manual_timing_rows_observed"] == 1
    assert result["runtime_probe_source_map"]["match_count"] == 1
    assert (tmp_path / LIVE_TIMING_ARTIFACT_NAME).exists()
    assert (tmp_path / PROBE_SOURCE_MAP_NAME).exists()
