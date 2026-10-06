"""Document shapes at the omnix_module_records boundary (WP-5.9)."""
from __future__ import annotations

import importlib.util
import json
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from pydantic import BaseModel

from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.document_schemas import DocumentShapeError, register_document_schema
from app.persistence.document_store import PostgresDocumentStore
from app.persistence.identity_service import ensure_local_identity
from app.persistence.module_repositories import PostgresModuleRecordRepository
from app.runtime.tenant_context import install_process_tenant
from tests.support.database import admin_database_url

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("OMNIX_TEST_DATABASE_URL"),
        reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
    ),
]


class _Card(BaseModel):
    title: str
    votes: int = 0


@pytest.fixture
def kind():
    database = PostgresDatabase(DatabaseSettings(url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=4))
    tenant = ensure_local_identity(database)
    install_process_tenant(tenant)
    record_type = f"shape-test-{uuid.uuid4().hex[:10]}"
    register_document_schema("test", record_type, _Card)
    try:
        yield database, tenant, record_type
    finally:
        with psycopg.connect(admin_database_url(), autocommit=True) as admin:
            admin.execute("DELETE FROM omnix_module_records WHERE record_type = %s", (record_type,))
        database.close()


def test_the_document_store_refuses_a_wrong_shape_and_stores_nothing(kind) -> None:
    database, _, record_type = kind
    documents = PostgresDocumentStore(database)
    documents.write({"title": "ok", "votes": 2}, module="test", record_type=record_type, record_id="a")
    with pytest.raises(DocumentShapeError):
        documents.write({"votes": "lots"}, module="test", record_type=record_type, record_id="b")
    with pytest.raises(DocumentShapeError):
        documents.update(lambda current: {"title": None}, module="test", record_type=record_type, record_id="a")
    with pytest.raises(DocumentShapeError):
        with documents.lock(module="test", record_type=record_type, record_id="c") as lock:
            lock.write({"title": "t", "votes": [1]})
    assert documents.read(module="test", record_type=record_type, record_id="a") == {"title": "ok", "votes": 2}
    assert documents.read(module="test", record_type=record_type, record_id="b") is None
    assert documents.read(module="test", record_type=record_type, record_id="c") is None


def test_the_module_record_repository_refuses_a_wrong_shape(kind) -> None:
    database, tenant, record_type = kind
    with database.transaction() as connection:
        repository = PostgresModuleRecordRepository(connection)
        with pytest.raises(DocumentShapeError):
            repository.put(tenant, module="test", record_type=record_type, record_id="x", payload={"votes": 1})
        stored = repository.put(tenant, module="test", record_type=record_type, record_id="y", payload={"title": "t"})
    assert stored["payload"] == {"title": "t"}


def _insert_raw(tenant, record_type: str, record_id: str, payload: object) -> None:
    with psycopg.connect(admin_database_url(), autocommit=True) as admin:
        admin.execute(
            "INSERT INTO omnix_module_records (workspace_id, module, record_type, record_id, payload)"
            " VALUES (%s, 'test', %s, %s, %s::jsonb)",
            (tenant.workspace_id, record_type, record_id, json.dumps(payload)),
        )


def test_an_old_document_with_another_shape_is_still_read_and_reported(kind, caplog) -> None:
    database, tenant, record_type = kind
    _insert_raw(tenant, record_type, "legacy", {"name": "written before the shape"})
    with caplog.at_level("WARNING"):
        value = PostgresDocumentStore(database).read(module="test", record_type=record_type, record_id="legacy")
    assert value == {"name": "written before the shape"}
    assert any(f"record_type={record_type} record_id=legacy" in record.getMessage() for record in caplog.records)


def test_the_check_script_lists_documents_that_do_not_match(kind) -> None:
    database, tenant, record_type = kind
    _insert_raw(tenant, record_type, "good", {"title": "fine"})
    _insert_raw(tenant, record_type, "bad", {"votes": "x"})
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("check_document_shapes", root / "scripts" / "check_document_shapes.py")
    assert spec is not None and spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    script.load_document_schemas()

    _, problems = script.check(database)
    mine = [line for line in problems if record_type in line]
    assert mine == [f"{tenant.workspace_id} test/{record_type}/bad: shape does not match"]
