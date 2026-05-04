import ast
from pathlib import Path


def _function_source_tree(path: str, function_name: str):
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(f"Function not found: {function_name}")


def test_run_autoplay_campaign_calls_prepare_manual_session():
    node = _function_source_tree("src/tests/rpg/autoplay_llm_campaign.py", "run_autoplay_campaign")
    calls = [
        subnode.func.id
        for subnode in ast.walk(node)
        if isinstance(subnode, ast.Call) and isinstance(subnode.func, ast.Name)
    ]

    assert "prepare_autoplay_manual_session" in calls


def test_call_turn_runtime_no_longer_accepts_server_base_url():
    node = _function_source_tree("src/tests/rpg/autoplay_llm_campaign.py", "_call_turn_runtime")
    arg_names = [arg.arg for arg in node.args.kwonlyargs]

    assert "base_url" not in arg_names
    assert "session_id" in arg_names
    assert "player_action" in arg_names