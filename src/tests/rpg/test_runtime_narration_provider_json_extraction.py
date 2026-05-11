from app.rpg.narration.runtime_narration_contract import (
    _apply_grounding_to_runtime_payload,
    _extract_json_object_from_provider_text,
    _extract_json_object_with_diagnostics_from_provider_text,
    _is_runtime_narration_candidate_envelope,
    _validate_parsed_provider_payload_or_parse_failure,
    validate_narration_payload,
)


def _candidate_json():
    return """
{
  "format_version": "rpg_narration_candidates_v1",
  "primary": {
    "format_version": "rpg_narration_v2",
    "narration": "Bran gives you 50 gold.",
    "action": "You receive 50 gold.",
    "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
    "reward": {"currency": {"gold": 50}},
    "followup_hooks": []
  },
  "safe_fallback": {
    "format_version": "rpg_narration_v2",
    "narration": "Bran does not hand over any coin.",
    "action": "The unsupported debt claim is refused.",
    "npc": {"speaker": "Bran", "line": "Sorry, friend. I do not owe you anything."},
    "reward": null,
    "followup_hooks": []
  }
}
"""


def test_extract_candidate_json_from_plain_provider_text():
    parsed = _extract_json_object_from_provider_text(_candidate_json())

    assert parsed["format_version"] == "rpg_narration_candidates_v1"
    assert _is_runtime_narration_candidate_envelope(parsed) is True


def test_extract_candidate_json_from_markdown_fence():
    raw = "```json\n" + _candidate_json() + "\n```"

    parsed = _extract_json_object_from_provider_text(raw)

    assert parsed["format_version"] == "rpg_narration_candidates_v1"
    assert _is_runtime_narration_candidate_envelope(parsed) is True


def test_extract_candidate_json_with_trailing_text():
    raw = "Here is the JSON:\n" + _candidate_json() + "\nHope this helps."

    parsed = _extract_json_object_from_provider_text(raw)

    assert parsed["format_version"] == "rpg_narration_candidates_v1"
    assert _is_runtime_narration_candidate_envelope(parsed) is True


def test_extracted_candidate_json_validates_without_old_v2_errors():
    raw = "Here is the JSON:\n" + _candidate_json() + "\n"
    parsed = _extract_json_object_from_provider_text(raw)

    validated = validate_narration_payload(
        parsed,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )

    assert validated["ok"] is True
    assert "invalid_format_version" not in validated["errors"]
    assert "missing_narration" not in validated["errors"]
    assert "npc_not_object" not in validated["errors"]
    assert validated["payload"]["format_version"] == "rpg_narration_candidates_v1"


def test_extracted_candidate_json_can_select_safe_fallback_after_primary_reward_rejected():
    parsed = _extract_json_object_from_provider_text(
        "```json\n" + _candidate_json() + "\n```"
    )

    validated = validate_narration_payload(
        parsed,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )
    assert validated["ok"] is True

    grounded = _apply_grounding_to_runtime_payload(
        validated["payload"],
        turn_contract={
            "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
            "current_location": "location:rusty_flagon_tavern",
            "state_delta": {},
            "result": {"summary": "Bran rejects the unsupported debt claim."},
        },
        simulation_state={},
        grounding_settings={
            "enabled": True,
            "primary_validation": True,
            "llm_safe_fallback_candidate": True,
            "deterministic_fallback": True,
        },
    )

    validation = grounded["grounding_validation"]

    assert validation["selected_candidate"] == "safe_fallback"
    assert validation["fallback_source"] == "llm_safe_fallback"
    assert validation["primary_rejected"] is True
    assert grounded["reward"] is None
    assert "do not owe" in grounded["npc"]["line"].lower()


def test_truncated_candidate_json_reports_parse_failure_with_candidate_marker():
    raw = """
{
  "format_version": "rpg_narration_candidates_v1",
  "primary": {
    "format_version": "rpg_narration_v2",
    "narration": "Bran starts to answer but
"""

    diagnostics = _extract_json_object_with_diagnostics_from_provider_text(raw)

    assert diagnostics["ok"] is False
    assert diagnostics["payload"] == {}
    assert diagnostics["contains_candidate_marker"] is True
    assert diagnostics["brace_balance"] > 0
    assert diagnostics["ends_with_brace"] is False
    assert diagnostics["error"]


def test_complete_candidate_json_with_fence_parses_successfully():
    raw = """```json
{
  "format_version": "rpg_narration_candidates_v1",
  "primary": {
    "format_version": "rpg_narration_v2",
    "narration": "Bran refuses the claim.",
    "action": "No coin changes hands.",
    "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
    "reward": null,
    "followup_hooks": []
  },
  "safe_fallback": {
    "format_version": "rpg_narration_v2",
    "narration": "Bran does not hand over any coin.",
    "action": "The unsupported claim is refused.",
    "npc": {"speaker": "Bran", "line": "Sorry, friend. I do not owe you anything."},
    "reward": null,
    "followup_hooks": []
  }
}
```"""

    diagnostics = _extract_json_object_with_diagnostics_from_provider_text(raw)

    assert diagnostics["ok"] is True
    assert diagnostics["payload"]["format_version"] == "rpg_narration_candidates_v1"
    assert diagnostics["strategy"] in {"direct", "first_brace_to_last_brace", "balanced_braces"}


def test_candidate_parse_failure_does_not_emit_old_v2_errors():
    validated = _validate_parsed_provider_payload_or_parse_failure(
        parsed_payload={},
        provider_call_diagnostics={
            "parsed_json_ok": False,
            "parsed_json_contains_candidate_marker": True,
            "parsed_json_error": "unterminated_json_object",
        },
        player_action="I ask Bran for a free room.",
    )

    assert validated["ok"] is False
    assert "provider_json_parse_failed_candidate_envelope" in validated["errors"]
    assert "invalid_format_version" not in validated["errors"]
    assert "missing_narration" not in validated["errors"]
    assert "npc_not_object" not in validated["errors"]