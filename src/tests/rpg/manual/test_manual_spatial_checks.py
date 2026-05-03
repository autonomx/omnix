from tests.rpg.manual.spatial_checks import run_spatial_checks
from tests.rpg.spatial.fixtures import tavern_spatial_fixture


def _result_with_graph(graph):
    return {
        "session": {
            "simulation_state": {
                "spatial_graph": graph,
            }
        }
    }


def test_manual_spatial_check_reads_graph_from_result_session():
    results = run_spatial_checks(
        checks=[
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "street",
                "expected_ok": True,
                "expected_reason": "passable",
            }
        ],
        result=_result_with_graph(tavern_spatial_fixture()),
    )

    assert results[0]["ok"] is True


def test_manual_spatial_check_reads_graph_from_explicit_session():
    results = run_spatial_checks(
        checks=[
            {
                "type": "spatial_visibility",
                "viewer": "player",
                "target": "bran",
                "expected_ok": True,
                "expected_reason": "same_area",
            }
        ],
        result={},
        session={
            "simulation_state": {
                "spatial_graph": tavern_spatial_fixture(),
            }
        },
    )

    assert results[0]["ok"] is True


def test_manual_spatial_check_missing_graph_fails_clearly():
    results = run_spatial_checks(
        checks=[
            {
                "type": "spatial_can_move",
                "from_area_id": "tavern_common_room",
                "to_area_id": "street",
                "expected_ok": True,
            }
        ],
        result={},
        session={},
    )

    assert results[0]["ok"] is False
    assert results[0]["error"] == "spatial_graph_missing"