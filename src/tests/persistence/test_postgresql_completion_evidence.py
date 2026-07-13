from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_corrective_migrations_are_complete_and_ordered() -> None:
    migration_root = _REPOSITORY_ROOT / "src" / "app" / "persistence" / "migrations"
    expected = [
        "0011_outbox_delivery_contract.sql",
        "0012_tenant_integrity_security.sql",
        "0013_coordinated_recovery.sql",
        "0014_runtime_coordination.sql",
        "0015_cutover_state_machine.sql",
        "0016_data_lifecycle_capacity.sql",
    ]
    assert [path.name for path in sorted(migration_root.glob("001*.sql")) if path.name >= "0011"] == expected


def test_corrective_contract_documents_exist() -> None:
    expected = [
        "docs/CENTRALIZED_POSTGRESQL_COMPLETION_FIXES_ROADMAP.md",
        "docs/architecture/POSTGRESQL_TRANSACTION_SCHEMA_CONTRACT.md",
        "docs/architecture/POSTGRESQL_OUTBOX_DELIVERY_CONTRACT.md",
        "docs/architecture/POSTGRESQL_COORDINATED_RECOVERY.md",
        "docs/architecture/POSTGRESQL_CURRENT_TOPOLOGY_CORRECTNESS.md",
        "docs/architecture/POSTGRESQL_CUTOVER_STATE_MACHINE.md",
        "docs/architecture/POSTGRESQL_DATA_LIFECYCLE_CAPACITY.md",
        "docs/architecture/POSTGRESQL_COMPLETION_EVIDENCE.md",
    ]
    for relative in expected:
        assert (_REPOSITORY_ROOT / relative).is_file(), relative


def test_c0_through_c7_are_verified_and_c8_is_finalizing() -> None:
    roadmap = (
        _REPOSITORY_ROOT / "docs" / "CENTRALIZED_POSTGRESQL_COMPLETION_FIXES_ROADMAP.md"
    ).read_text(encoding="utf-8")
    for phase in range(8):
        line = next(line for line in roadmap.splitlines() if line.startswith(f"| C{phase} —"))
        assert "| verified |" in line
    c8 = next(line for line in roadmap.splitlines() if line.startswith("| C8 —"))
    assert "| in_progress |" in c8


def test_evidence_ledger_records_every_verified_phase_head() -> None:
    evidence = (
        _REPOSITORY_ROOT / "docs" / "architecture" / "POSTGRESQL_COMPLETION_EVIDENCE.md"
    ).read_text(encoding="utf-8")
    for phase in range(8):
        assert f"| C{phase} |" in evidence
    assert "continuous 1,000-turn public apply-turn endurance" in evidence
    assert "GitHub Actions remain provider-free" in evidence
