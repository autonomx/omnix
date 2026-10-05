
from app.apps.rpg.npc_evolution.profile_store import (
    profile_path_for_npc,
)


def test_profile_path_collapses_prefixed_npc_id(tmp_path):
    assert profile_path_for_npc("npc:bran", root=tmp_path).name == "bran.json"
