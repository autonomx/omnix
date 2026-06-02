from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_phase0_runtime_facade_loads_split_parts_monotonically():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()
    part_numbers = [int(name.removeprefix("runtime_part")) for name in manifest["part_modules"]]

    assert part_numbers == list(range(1, max(part_numbers) + 1))
    assert manifest["part_modules"][-5:] == [
        "runtime_part22",
        "runtime_part23",
        "runtime_part24",
        "runtime_part25",
        "runtime_part26",
    ]


def test_phase0_combat_contract_bridges_emit_source_fields():
    assert '"source": "deterministic_combat_reward_contract"' in _read(
        "src/app/rpg/session/runtime_part24.py"
    )
    assert '"source": "deterministic_combat_quest_sync"' in _read(
        "src/app/rpg/session/runtime_part25.py"
    )
    assert '"source": "deterministic_combat_quest_sync_contract"' in _read(
        "src/app/rpg/session/runtime_part26.py"
    )


def test_phase0_runtime_wrapper_drift_report_is_authoritative():
    from app.rpg.session import runtime

    report = runtime.get_runtime_wrapper_drift_report()

    assert report["ok"] is True
    assert report["missing_combat_contract_modules"] == []
    assert report["unexpected_combat_contract_modules"] == []
    assert report["actual_combat_contract_modules"] == report[
        "expected_combat_contract_modules"
    ]


def test_phase0_deterministic_ci_has_no_live_provider_requirements():
    workflow = _read(".github/workflows/rpg-pr-deterministic.yml")
    forbidden_tokens = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "LM_STUDIO",
        "LMSTUDIO",
    ]

    assert "RPG_TEST_MODE: deterministic" in workflow
    for token in forbidden_tokens:
        assert token not in workflow
