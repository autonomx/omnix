from pathlib import Path


def test_v3_migration_persists_binding_authority_trigger_plans_and_manifests():
    migration = Path(
        "src/app/persistence/migrations/0083_trading_evidence_execution_v3.sql"
    ).read_text(encoding="utf-8")

    for token in (
        "binding_purpose",
        "ibkr:%",
        "'quarantined'",
        "omnix_trading_trigger_plans",
        "TRIGGER_ORDER_UNRESOLVED",
        "omnix_trading_session_evidence_manifests",
        "PERMANENTLY_UNSCORABLE",
    ):
        assert token in migration
