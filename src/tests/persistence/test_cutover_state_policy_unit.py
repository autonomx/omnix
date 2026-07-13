from __future__ import annotations

import pytest

from app.persistence.cutover_state import (
    CutoverTransitionError,
    PostgresCutoverStateRepository,
    validate_transition_request,
)


_ORDER = (
    "legacy_preflight",
    "imported_unverified",
    "imported_verified",
    "postgresql_activated_frozen",
    "postgresql_open_for_writes",
    "postgresql_stabilized",
)


class _Result:
    def __init__(self, row=None, rows=None, *, rowcount: int = 1) -> None:
        self._row = row
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _CutoverConnection:
    def __init__(self, *, backup_verified: bool = True, import_clean: bool = True) -> None:
        self.mode = "legacy_preflight"
        self.state = "legacy_preflight"
        self.import_id = None
        self.source_hash = None
        self.backup_id = None
        self.latest_revision = None
        self.backup_verified = backup_verified
        self.import_clean = import_clean
        self.transitions: list[tuple[str, str]] = []

    def _current_row(self):
        return (
            self.mode,
            self.state,
            self.import_id,
            self.source_hash,
            self.backup_id,
            None,
            None,
            None,
            None,
            self.latest_revision,
            None,
            {},
        )

    def execute(self, sql: str, parameters=None):
        normalized = " ".join(sql.split())
        parameters = tuple(parameters or ())
        if normalized.startswith("SELECT mode, authority_state"):
            return _Result(self._current_row())
        if normalized.startswith("SELECT status, source_hash FROM omnix_legacy_import_runs"):
            return _Result(
                ("completed", "a" * 64) if self.import_clean else ("failed", "a" * 64)
            )
        if normalized.startswith("SELECT status, verification FROM omnix_legacy_import_runs"):
            return _Result(
                ("completed", {"ok": True})
                if self.import_clean
                else ("completed", {"ok": False})
            )
        if normalized.startswith("SELECT status FROM omnix_backup_generations"):
            return _Result(("verified" if self.backup_verified else "failed",))
        if normalized.startswith("UPDATE omnix_persistence_cutover"):
            self.mode = str(parameters[0])
            self.state = str(parameters[1])
            self.import_id = parameters[2] or self.import_id
            self.source_hash = parameters[3] or self.source_hash
            self.backup_id = parameters[4] or self.backup_id
            self.latest_revision = parameters[10] or self.latest_revision
            return _Result(self._current_row())
        if normalized.startswith("INSERT INTO omnix_cutover_transitions"):
            self.transitions.append((str(parameters[0]), str(parameters[1])))
            return _Result()
        raise AssertionError(f"unexpected SQL: {normalized}")


def _requirements(target: str) -> dict[str, object]:
    values: dict[str, object] = {
        "software_revision": "test-head",
        "schema_version": "0016_data_lifecycle_capacity",
    }
    if target in {
        "postgresql_activated_frozen",
        "postgresql_open_for_writes",
        "postgresql_stabilized",
        "rollback_recorded",
    }:
        values["operator_note"] = "operator evidence"
    if target == "postgresql_open_for_writes":
        values["write_reopen_acknowledged"] = True
    if target == "postgresql_stabilized":
        values["latest_authoritative_revision"] = "campaign:1@42"
    return values


def test_every_forward_authority_transition_is_valid() -> None:
    for source, target in zip(_ORDER, _ORDER[1:]):
        validate_transition_request(from_state=source, to_state=target, **_requirements(target))


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("legacy_preflight", "imported_verified"),
        ("imported_unverified", "postgresql_activated_frozen"),
        ("imported_verified", "postgresql_open_for_writes"),
        ("postgresql_activated_frozen", "postgresql_stabilized"),
        ("postgresql_open_for_writes", "imported_verified"),
        ("postgresql_stabilized", "postgresql_open_for_writes"),
    ],
)
def test_skipped_and_backward_transitions_fail(source: str, target: str) -> None:
    with pytest.raises(CutoverTransitionError, match="invalid cutover transition"):
        validate_transition_request(from_state=source, to_state=target, **_requirements(target))


def test_opening_writes_requires_acknowledgement() -> None:
    with pytest.raises(CutoverTransitionError, match="acknowledgement"):
        validate_transition_request(
            from_state="postgresql_activated_frozen",
            to_state="postgresql_open_for_writes",
            software_revision="test-head",
            schema_version="schema",
            operator_note="operator evidence",
        )


def test_stabilization_requires_note_and_latest_revision() -> None:
    with pytest.raises(CutoverTransitionError, match="operator note"):
        validate_transition_request(
            from_state="postgresql_open_for_writes",
            to_state="postgresql_stabilized",
            software_revision="test-head",
            schema_version="schema",
            latest_authoritative_revision="campaign:1@42",
        )
    with pytest.raises(CutoverTransitionError, match="latest authoritative revision"):
        validate_transition_request(
            from_state="postgresql_open_for_writes",
            to_state="postgresql_stabilized",
            software_revision="test-head",
            schema_version="schema",
            operator_note="operator evidence",
        )


def test_post_write_rollback_requires_note_and_destructive_acknowledgement() -> None:
    with pytest.raises(CutoverTransitionError, match="destructive acknowledgement"):
        validate_transition_request(
            from_state="postgresql_open_for_writes",
            to_state="rollback_recorded",
            software_revision="test-head",
            schema_version="schema",
            operator_note="accepted loss",
        )


def test_activation_requires_verified_backup_generation() -> None:
    connection = _CutoverConnection(backup_verified=False)
    repository = PostgresCutoverStateRepository(connection)
    repository.transition(
        to_state="imported_unverified",
        software_revision="test-head",
        schema_version="schema",
        import_run_id="legacy-import:test",
    )
    repository.transition(
        to_state="imported_verified",
        software_revision="test-head",
        schema_version="schema",
        import_run_id="legacy-import:test",
    )
    with pytest.raises(CutoverTransitionError, match="verified recovery generation"):
        repository.transition(
            to_state="postgresql_activated_frozen",
            software_revision="test-head",
            schema_version="schema",
            backup_generation_id="backup:test",
            operator_note="operator evidence",
        )


def test_repository_records_every_valid_transition() -> None:
    connection = _CutoverConnection()
    repository = PostgresCutoverStateRepository(connection)
    repository.transition(
        to_state="imported_unverified",
        software_revision="test-head",
        schema_version="schema",
        import_run_id="legacy-import:test",
    )
    repository.transition(
        to_state="imported_verified",
        software_revision="test-head",
        schema_version="schema",
        import_run_id="legacy-import:test",
    )
    repository.transition(
        to_state="postgresql_activated_frozen",
        software_revision="test-head",
        schema_version="schema",
        backup_generation_id="backup:test",
        operator_note="restore rehearsed",
    )
    repository.transition(
        to_state="postgresql_open_for_writes",
        software_revision="test-head",
        schema_version="schema",
        operator_note="lossless legacy rollback ends",
        write_reopen_acknowledged=True,
    )
    repository.transition(
        to_state="postgresql_stabilized",
        software_revision="test-head",
        schema_version="schema",
        operator_note="window healthy",
        latest_authoritative_revision="campaign:1@42",
    )
    assert connection.transitions == list(zip(_ORDER, _ORDER[1:]))
