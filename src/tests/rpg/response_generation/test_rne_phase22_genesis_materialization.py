from __future__ import annotations

from pathlib import Path

from app.rpg.session.genesis.launch_readiness import (
    campaign_launch_readiness,
    dossier_readiness,
)
from app.rpg.session.genesis.pipeline_adapter import create_new_game_from_genesis_payload


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_new_game_generates_bible_dossiers_progress_and_launch_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_RPG_SESSION_DIR", str(tmp_path))
    result = create_new_game_from_genesis_payload(
        {
            "contract_version": "rpg_genesis_v2",
            "campaign_template": "summoned_heroes",
            "genre": "portal_fantasy",
            "tone": "fractured mythic fantasy",
            "identity": {"name": "Aria", "pronouns": "she/her"},
            "world_options": {
                "starting_location": "vanta_gate",
                "difficulty": "normal",
                "world_activity": "living_world",
                "economy_pressure": "normal",
                "combat_lethality": "deadly",
                "seed": 42,
            },
            "world_forge": {
                "enabled": True,
                "depth": "quick",
                "background_expansion": False,
            },
        }
    )
    assert result["ok"] is True, result
    assert result["status"] == "ready"
    assert result["creation_progress"]["launch_ready"] is True
    assert result["creation_progress"]["completed_jobs"] > 0
    session = result["session"]
    assert campaign_launch_readiness(session)["ready"] is True
    assert session["manifest"]["campaign_generation_status"] == "ready"
    bible = session["state"]["campaign_bible"]
    assert bible["canon_revision"] == 1
    assert bible["lore_pages"]
    vexira = session["state"]["npc_dossiers"]["npc:vexira_umbra"]
    assert vexira["appearance"]
    assert dossier_readiness(session, "npc:vexira_umbra")["ready"] is True
    assert dossier_readiness(session, "location:vanta_gate")["ready"] is True
    assert result["campaign_genesis_persistence"]["mode"] in {
        "postgresql_authority",
        "portable_projection_only",
    }


def test_dossier_gate_rejects_incomplete_visible_actor() -> None:
    session = {
        "state": {
            "npc_dossiers": {
                "npc:thin": {
                    "id": "npc:thin",
                    "name": "Thin",
                    "dossier_status": "incomplete",
                }
            }
        }
    }
    readiness = dossier_readiness(session, "npc:thin")
    assert readiness["ready"] is False
    assert {"appearance", "personality", "backstory"}.issubset(readiness["missing_fields"])


def test_foreground_gateway_checks_genesis_before_authoritative_turn() -> None:
    source = (REPO_ROOT / "src" / "app" / "gateway" / "rpg_turn_pipeline.py").read_text(
        encoding="utf-8"
    )
    gate = source.index("require_campaign_launch_ready")
    apply_turn = source.index("interactive_first_call_runtime.apply_turn")
    assert gate < apply_turn
    assert "campaign_genesis_incomplete" in source
