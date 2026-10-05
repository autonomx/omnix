from __future__ import annotations

from app.persistence.cutover import LEGACY_BUNDLE_FORMAT, PostgresLegacyImporter
from app.runtime.tenant_context import local_tenant_context


def test_dry_run_importer_does_not_apply_or_require_schema_migrations():
    importer = PostgresLegacyImporter(database=object())
    report = importer.import_bundle(
        local_tenant_context(),
        {
            "format_version": LEGACY_BUNDLE_FORMAT,
            "source_id": "dry-run-no-database",
            "entities": {},
            "source_inventory": [],
        },
        dry_run=True,
    )

    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["preflight"]["counts"] == {}
