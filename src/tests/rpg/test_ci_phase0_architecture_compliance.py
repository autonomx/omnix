from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DETERMINISTIC_RPG_BOUNDARY_ROOTS = [
    "src/app/rpg/combat",
    "src/app/rpg/interactions",
    "src/app/rpg/progression",
    "src/app/rpg/session",
]
FORBIDDEN_LIVE_PROVIDER_IMPORT_PREFIXES = [
    "app.providers",
    "openai",
    "anthropic",
    "app.llm",
]
ALLOWED_PROVIDER_INTERFACE_IMPORTS = {
    "app.providers.base",
}
EXPECTED_COMBAT_CONTRACT_PARTS = [
    "runtime_part22",
    "runtime_part23",
    "runtime_part24",
    "runtime_part25",
    "runtime_part26",
]
REQUIRED_RPG_WORKFLOWS = [
    ".github/workflows/rpg-pr-deterministic.yml",
    ".github/workflows/rpg-phase0-architecture-compliance.yml",
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _python_files_under(path: str):
    root = REPO_ROOT / path
    return sorted(item for item in root.rglob("*.py") if item.is_file())


def _module_is_allowed_provider_interface(module: str) -> bool:
    return module in ALLOWED_PROVIDER_INTERFACE_IMPORTS


def _module_is_forbidden(module: str) -> bool:
    if _module_is_allowed_provider_interface(module):
        return False
    return any(
        module == forbidden or module.startswith(f"{forbidden}.")
        for forbidden in FORBIDDEN_LIVE_PROVIDER_IMPORT_PREFIXES
    )


def _runtime_part_from_module(module: str) -> str:
    return module.rsplit(".", 1)[-1]


def _find_forbidden_imports(path: Path) -> list[str]:
    violations = []
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if line.startswith("import "):
            imported_modules = line.removeprefix("import ").split(",")
            for imported in imported_modules:
                module = imported.strip().split(" as ", 1)[0]
                if _module_is_forbidden(module):
                    violations.append(f"line {lineno}: import {module}")
        elif line.startswith("from ") and " import " in line:
            module = line.removeprefix("from ").split(" import ", 1)[0].strip()
            if _module_is_forbidden(module):
                violations.append(f"line {lineno}: from {module} import ...")
    return violations


def test_phase0_runtime_facade_loads_split_parts_monotonically():
    from app.rpg.session import runtime

    manifest = runtime.get_runtime_wrapper_manifest()
    part_modules = list(manifest["part_modules"])
    part_numbers = [int(name.removeprefix("runtime_part")) for name in part_modules]
    combat_contract_parts = [
        _runtime_part_from_module(module)
        for module in manifest["combat_contract_modules"]
    ]

    assert part_numbers == list(range(1, max(part_numbers) + 1))
    assert combat_contract_parts == EXPECTED_COMBAT_CONTRACT_PARTS
    for part_name in EXPECTED_COMBAT_CONTRACT_PARTS:
        assert part_name in part_modules


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


def test_phase0_required_rpg_ci_workflows_are_not_path_filtered():
    for workflow_path in REQUIRED_RPG_WORKFLOWS:
        workflow = _read(workflow_path)
        assert "pull_request:" in workflow
        assert "branches: [rpg]" in workflow
        assert "push:" in workflow
        assert "paths:" not in workflow


def test_phase0_deterministic_layers_do_not_import_live_providers():
    violations = []
    for root in DETERMINISTIC_RPG_BOUNDARY_ROOTS:
        for path in _python_files_under(root):
            relative = path.relative_to(REPO_ROOT).as_posix()
            for violation in _find_forbidden_imports(path):
                violations.append(f"{relative}: {violation}")

    assert violations == []
