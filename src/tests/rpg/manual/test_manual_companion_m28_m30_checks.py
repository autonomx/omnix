from app.rpg.npc_evolution.state import apply_npc_evolution_delta, start_npc_arc
from app.rpg.social.reputation import set_relationship_values
from tests.rpg.manual.companion_m28_m30_checks import run_companion_m28_m30_checks


def _setup(session):
    start_npc_arc(
        session["simulation_state"],
        "bran",
        "npc_arc:bran_revenge",
        motivation="revenge_against_red_sashes",
        role="companion",
    )
    apply_npc_evolution_delta(session["simulation_state"], "bran", companion_eligible=True)
    set_relationship_values(session["simulation_state"], "bran", {"trust": 80})


def test_manual_companion_offer_evaluate_check():
    session = {"simulation_state": {}}
    _setup(session)

    result = run_companion_m28_m30_checks(
        checks=[
            {
                "type": "companion_offer_evaluate",
                "npc_id": "bran",
                "expected_eligible": True,
                "expected_reason": "eligible",
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_companion_offer_accept_check_adds_party_member():
    session = {"simulation_state": {}}
    _setup(session)

    accept = run_companion_m28_m30_checks(
        checks=[
            {
                "type": "companion_offer_accept",
                "npc_id": "bran",
                "expected_ok": True,
            }
        ],
        result={},
        session=session,
    )[0]
    member = run_companion_m28_m30_checks(
        checks=[
            {
                "type": "party_member",
                "npc_id": "bran",
                "expected_present": True,
            }
        ],
        result={},
        session=session,
    )[0]

    assert accept["ok"] is True
    assert member["ok"] is True