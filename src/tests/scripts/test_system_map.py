"""The system map (docs/architecture/omnix-system-map.*) stays true to the code and answers agents' questions."""
from __future__ import annotations

from scripts import system_map


def test_the_map_cites_only_paths_that_exist_and_every_flow_hop_has_an_edge() -> None:
    _, problems = system_map.build()
    assert problems == []


def test_the_committed_map_is_a_fresh_build() -> None:
    assert system_map.stale_files() == [], "regenerate with: python scripts/system_map.py build"


def test_feature_edges_are_the_ones_feature_py_declares() -> None:
    the_map, _ = system_map.build()
    by_feature = {n["feature_id"]: n["id"] for n in the_map["nodes"] if n.get("feature_id")}
    declared = {
        (by_feature[feature_id], by_feature[other], kind)
        for feature_id, feature in system_map.catalog_features().items()
        for kind in ("depends_on", "uses")
        for other in feature[kind]
    }
    drawn = {(e["from"], e["to"], e["kind"]) for e in the_map["edges"] if e["kind"] in ("depends_on", "uses")}
    assert drawn == declared
    assert ("live_voice", "chat", "depends_on") in drawn
    assert ("trading", "research", "uses") in drawn
    mounted = {e["to"] for e in the_map["edges"] if e["kind"] == "mounts"}
    assert "live_speech" not in mounted  # opt-in: mounted only when named
    assert "chat" in mounted


def test_a_missing_path_is_a_problem(monkeypatch) -> None:
    node = dict(system_map.data.NODES[0], paths=["no/such/dir/"])
    monkeypatch.setattr(system_map.data, "NODES", [node, *system_map.data.NODES[1:]])
    _, problems = system_map.build()
    assert f"{node['id']}: missing path no/such/dir/" in problems


def test_owner_is_the_longest_cited_path() -> None:
    the_map = system_map.load()
    assert system_map.owner_of("src/app/apps/rpg/edge/hermes/feature.py", the_map) == "hermes_rpg"
    assert system_map.owner_of("src/app/apps/rpg/session/turn/run.py", the_map) == "rpg"
    assert system_map.owner_of(str(system_map.ROOT / "src/app/platform/live_voice/pipeline.py"), the_map) == "live_voice"
    assert system_map.owner_of("nowhere/at/all.py", the_map) is None


def test_queries_answer_briefly() -> None:
    the_map = system_map.load()
    node = system_map.node_text(the_map, system_map.find_node(the_map, "live-voice"))
    assert node.startswith("live_voice — ")
    assert "invariants:" in node and "flows: live_call_turn" in node
    flow = system_map.flow_text(the_map, "rpg_turn")
    assert " 1. web_rpg:" in flow
    assert "returns from providers over rpg calls providers" in flow
    assert system_map.flow_text(the_map, "no_such_flow") is None
    # each answer is a small slice of the whole map
    whole = len(system_map.JSON_PATH.read_text(encoding="utf-8"))
    assert len(node) < whole / 20 and len(flow) < whole / 20


def test_the_cli_reports_unknown_names_with_suggestions(capsys) -> None:
    assert system_map.main(["node", "livevoice"]) == 1
    assert "did you mean: live_voice" in capsys.readouterr().out
