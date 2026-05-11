from tests.rpg.manual.scenario_execution import _is_n101_gate_warning


def test_n101_warning_promotion_markers():
    assert _is_n101_gate_warning("npc_bran_refuses_fake_debt:turn_1:n101_fake_debt_used_deterministic_fallback")
    assert _is_n101_gate_warning("npc_bran_refuses_fake_debt:turn_1:fake_debt_unexpected_selected_candidate:deterministic_fallback")
    assert _is_n101_gate_warning("scenario:turn_1:grounding_primary_violation:unsupported_reward_claim")
    assert _is_n101_gate_warning("scenario:turn_1:grounding_fallback_used:deterministic_fallback:deterministic_fallback")
    assert not _is_n101_gate_warning("ordinary_non_gate_warning")