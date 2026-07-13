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


def test_c0_through_c8_are_verified() -> None:
    roadmap = (
        _REPOSITORY_ROOT / "docs" / "CENTRALIZED_POSTGRESQL_COMPLETION_FIXES_ROADMAP.md"
    ).read_text(encoding="utf-8")
    assert "**Status:** Verified complete" in roadmap
    for phase in range(9):
        line = next(line for line in roadmap.splitlines() if line.startswith(f"| C{phase} —"))
        assert "| verified |" in line


def test_evidence_ledger_records_every_verified_phase_head() -> None:
    evidence = (
        _REPOSITORY_ROOT / "docs" / "architecture" / "POSTGRESQL_COMPLETION_EVIDENCE.md"
    ).read_text(encoding="utf-8")
    for phase in range(9):
        assert f"| C{phase} |" in evidence
    assert "4374619b2d8d192330b6c45c62c7658536e1f1a3" in evidence
    assert "| C8 |" in evidence and "| 4315 | 233 | 505 | 4578 |" in evidence
    assert "continuous 1,000-turn public apply-turn endurance" in evidence
    assert "GitHub Actions remain provider-free" in evidence
