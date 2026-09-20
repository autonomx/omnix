from __future__ import annotations

from dataclasses import replace

from app.persistence.migrations import (
    _checksum_is_accepted,
    discover_migrations,
)


def test_known_0083_historical_checksums_are_accepted_but_unknown_drift_is_not():
    migration = next(
        item
        for item in discover_migrations()
        if item.version == "0083_trading_evidence_execution_v3"
    )
    assert migration.checksum == (
        "44753b480f6fa7b74bbd52d1c5f5f2142e52e8b6a5f776ed7cd44900a2b20ca0"
    )

    historical = (
        "221d3953a6e0e43c6482f2a0604fdadfdc203e10c85b88ae10e450b2a3082877",
        "37abdf0f320e07b8c43dc6a1fcd8cf7adc657bd4fae010b3b905bbd55c9aeb1c",
        "453e6d11f5d9cd33d159c0cef4b736088fb83c96b02bca11a9da7b3149472aab",
    )

    assert all(_checksum_is_accepted(migration, checksum) for checksum in historical)
    assert _checksum_is_accepted(migration, migration.checksum)
    assert not _checksum_is_accepted(migration, "0" * 64)
    assert not _checksum_is_accepted(
        replace(migration, checksum="1" * 64), historical[0]
    )
