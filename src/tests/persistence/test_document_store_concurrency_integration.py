"""Document-store conditional writes (WP-5.9)."""
from __future__ import annotations

import os
import threading
import uuid

import psycopg
import pytest

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.document_schemas import register_document_schema
from app.persistence.document_store import DocumentLock, DocumentRevisionConflict, PostgresDocumentStore
from app.persistence.identity_service import ensure_local_identity
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


@pytest.fixture
def store():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=12))
    install_process_tenant(ensure_local_identity(database))
    record_type = f"cas-test-{uuid.uuid4().hex[:10]}"
    register_document_schema("test", record_type, dict)
    try:
        yield PostgresDocumentStore(database), record_type
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_module_records WHERE record_type = %s", (record_type,))
        database.close()


def test_a_stale_revision_is_rejected(store) -> None:
    documents, record_type = store
    first = documents.write({"n": 1}, module="test", record_type=record_type, expected_revision=0)
    with pytest.raises(DocumentRevisionConflict):
        documents.write({"n": 2}, module="test", record_type=record_type, expected_revision=0)
    documents.write({"n": 2}, module="test", record_type=record_type, expected_revision=first)
    with pytest.raises(DocumentRevisionConflict):
        documents.write({"n": 3}, module="test", record_type=record_type, expected_revision=first)
    assert documents.read_versioned(module="test", record_type=record_type) == ({"n": 2}, first + 1)


def test_concurrent_updates_are_not_lost(store) -> None:
    documents, record_type = store

    def add(index: int) -> None:
        documents.update(
            lambda current: {**dict(current or {}), f"k{index}": index},
            module="test", record_type=record_type, default={}, attempts=50,
        )

    threads = [threading.Thread(target=add, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert documents.read(module="test", record_type=record_type) == {f"k{index}": index for index in range(8)}


def test_document_lock_serializes_read_modify_write(store) -> None:
    documents, record_type = store
    locks = [DocumentLock(PostgresDocumentStore(documents.database), module="test", record_type=record_type) for _ in range(6)]

    def increment(lock: DocumentLock) -> None:
        for _ in range(5):
            with lock:
                current = lock.read(default={"n": 0})
                lock.write({"n": int(current["n"]) + 1})

    threads = [threading.Thread(target=increment, args=(lock,)) for lock in locks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert documents.read(module="test", record_type=record_type) == {"n": 30}
