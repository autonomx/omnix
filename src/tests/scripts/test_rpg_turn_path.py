"""scripts/rpg_turn_path.py writes [rpg_turn_path] in place, and the stored list names real RPG modules (RQ-0.7)."""
from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("omnix_rpg_turn_path_tests_target", ROOT / "scripts/rpg_turn_path.py")
turn_path = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(turn_path)


def test_the_section_is_appended_once_then_replaced(tmp_path, monkeypatch) -> None:
    layers = tmp_path / "layers.toml"
    layers.write_text('[production]\nentrypoints = ["src/main.py"]\n', encoding="utf-8")
    monkeypatch.setattr(turn_path, "LAYERS", layers)

    turn_path.write_turn_path(["app.apps.rpg.a", "app.apps.rpg.b"], ["suite"])
    turn_path.write_turn_path(["app.apps.rpg.c"], ["suite"])

    text = layers.read_text(encoding="utf-8")
    assert text.count("[rpg_turn_path]") == 1 and text.count("# RQ-0.7") == 1
    config = tomllib.loads(text)
    assert config["rpg_turn_path"]["modules"] == ["app.apps.rpg.c"]
    assert config["production"]["entrypoints"] == ["src/main.py"]


def test_only_function_bodies_count_as_called(tmp_path) -> None:
    source = tmp_path / "module.py"
    source.write_text("X = 1\n\n\ndef f():\n    return X\n\n\nclass C:\n    def m(self):\n        return 2\n", encoding="utf-8")
    assert turn_path.function_body_lines(source) == {5, 10}


def test_the_recorded_turn_path_names_rpg_modules_that_exist() -> None:
    modules = tomllib.loads((ROOT / "resources/architecture/layers.toml").read_text(encoding="utf-8"))["rpg_turn_path"]["modules"]
    assert modules == sorted(modules) and len(modules) == len(set(modules))
    sources = turn_path.rpg_sources()
    assert [name for name in modules if name not in sources] == []
    assert "app.apps.rpg.edge.api.turn_pipeline" in modules
