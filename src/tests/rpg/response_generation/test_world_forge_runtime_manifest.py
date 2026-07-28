from app.rpg.session.genesis.canon_compiler import CanonCompilationResult
from app.rpg.session.genesis.world_forge_pipeline import _attach_runtime_bootstrap
from app.rpg.world.causal_runtime import (
    advance_installed_causal_runtime,
    bootstrap_causal_runtime,
)


def _planning_topics():
    return {
        "present_day_state": {
            "state": {
                "ent:regions:001": {
                    "political_stability": 60,
                    "trade_access": 50,
                    "resource_access": 70,
                    "population_index": 55,
                }
            }
        },
        "political_claim_graph": {"claims": []},
        "settlement_origin_plan": {"settlements": []},
        "culture_lineage_plan": {"lineages": []},
        "pressure_plan": {
            "pressures": [
                {
                    "pressure_id": "pressure:001",
                    "severity": 30,
                    "trend": "escalating",
                    "next_tick_delta": {
                        "target_id": "ent:regions:001",
                        "dimension": "political_stability",
                        "operation": "decrease",
                        "value": 4,
                    },
                    "escalation_threshold": 32,
                    "resolution_threshold": 20,
                }
            ]
        },
    }


def test_runtime_bootstrap_is_certified_inside_campaign_manifest() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics())
    compilation = CanonCompilationResult(
        document={
            "schema_version": "rpg_campaign_bible_v2",
            "manifest": {"entity_count": 1},
            "content_hash": "sha256:old",
        },
        completeness={},
        retrieval_index={},
        launch_ready=True,
        metadata={"content_hash": "sha256:old"},
    )

    updated = _attach_runtime_bootstrap(compilation, runtime)

    assert updated.document["manifest"]["causal_runtime_bootstrap"] == runtime
    assert updated.document["content_hash"].startswith("sha256:")
    assert updated.document["content_hash"] != "sha256:old"
    assert updated.metadata["content_hash"] == updated.document["content_hash"]
    assert updated.metadata["causal_runtime_hash"] == runtime["runtime_hash"]


def test_materialized_manifest_is_lazily_installed_on_first_tick() -> None:
    runtime = bootstrap_causal_runtime(_planning_topics())
    simulation_state = {
        "campaign_bible": {
            "manifest": {"causal_runtime_bootstrap": runtime}
        }
    }

    advanced, emitted = advance_installed_causal_runtime(simulation_state, tick=1)

    assert simulation_state["causal_world_runtime"] == advanced
    assert advanced["last_tick"] == 1
    assert [event.event_type for event in emitted] == [
        "pressure_tick",
        "pressure_escalated",
    ]
