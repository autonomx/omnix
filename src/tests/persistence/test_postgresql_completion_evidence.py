from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_corrective_migrations_are_complete_and_ordered() -> None:
    migration_root = _REPOSITORY_ROOT / "src" / "app" / "persistence" / "migrations"
    corrective = [
        "0011_outbox_delivery_contract.sql",
        "0012_tenant_integrity_security.sql",
        "0013_coordinated_recovery.sql",
        "0014_runtime_coordination.sql",
        "0015_cutover_state_machine.sql",
        "0016_data_lifecycle_capacity.sql",
    ]
    discovered = [
        path.name
        for path in sorted(migration_root.glob("001*.sql"))
        if path.name >= "0011"
    ]
    assert discovered[: len(corrective)] == corrective
    assert discovered == sorted(set(discovered))
