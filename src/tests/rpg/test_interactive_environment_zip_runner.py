from __future__ import annotations

from tests.rpg import interactive_environment_feature_matrix_zip as envzip


def test_environment_zip_runner_selects_named_scenario() -> None:
    selected = envzip._select_environment_scenarios(["terrain_memory_probe"])

    assert [scenario.scenario_id for scenario in selected] == ["terrain_memory_probe"]


def test_environment_zip_runner_requires_live_provider(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        envzip,
        "run_environment_feature_matrix",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    exit_code = envzip.main([])

    assert exit_code == 2
    assert "--live-provider" in capsys.readouterr().out
