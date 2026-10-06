"""Audiobook uploads are streamed and capped (WP-8.7)."""
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.apps.audiobook import extraction
from app.apps.audiobook import routes as audiobook_routes
from app.apps.audiobook.extraction import UnsupportedSource
from app.apps.audiobook.service import AudiobookService
from app.persistence.blob_store import LocalBlobStore


def _client(monkeypatch, service) -> TestClient:
    monkeypatch.setattr(audiobook_routes, "_service_and_context", lambda: (service, None))
    gateway = FastAPI()
    gateway.include_router(audiobook_routes.create_audiobook_router())
    return TestClient(gateway)


def test_source_upload_reaches_the_service_as_a_stream(monkeypatch):
    received = {}

    def submit_source(_context, *, content, **kwargs):
        received["stream"] = content
        received["body"] = content.read()
        return {"project_id": kwargs["project_id"], "source_asset_id": "asset", "job_id": "job"}

    client = _client(monkeypatch, SimpleNamespace(submit_source=submit_source))
    response = client.post(
        "/api/audiobook/projects/book/source?source_format=txt",
        content=iter([b"Chapter one. ", b"It begins."]),
    )

    assert response.status_code == 202
    assert received["body"] == b"Chapter one. It begins."
    assert not isinstance(received["stream"], bytes)
    assert received["stream"].closed


@pytest.mark.parametrize("route,limit", [
    ("/api/audiobook/projects/book/source?source_format=txt", "source"),
    ("/api/audiobook/projects/book/cover", "cover"),
])
def test_chunked_uploads_are_refused_once_past_the_cap(monkeypatch, route, limit):
    monkeypatch.setattr(extraction, "MAX_SOURCE_BYTES", 8)
    monkeypatch.setattr(audiobook_routes, "_MAX_COVER_BYTES", 8)
    service = SimpleNamespace(
        submit_source=lambda *_args, **_kwargs: pytest.fail("oversized source reached the service"),
        set_cover=lambda *_args, **_kwargs: pytest.fail("oversized cover reached the service"),
    )

    # A generator body is sent chunked, with no Content-Length to check.
    response = _client(monkeypatch, service).post(route, content=iter([b"12345", b"67890"]))

    assert response.status_code == 413
    assert response.json() == {"detail": f"{limit} is too large"}


def test_cover_upload_passes_the_raw_body(monkeypatch):
    covers = []

    def set_cover(_context, **kwargs):
        covers.append(kwargs)
        return {"cover_asset_id": "cover", "mime_type": "image/png"}

    response = _client(monkeypatch, SimpleNamespace(set_cover=set_cover)).post(
        "/api/audiobook/projects/book/cover?filename=front.png", content=b"\x89PNG-bytes",
    )

    assert response.status_code == 200
    assert covers == [{"project_id": "book", "content": b"\x89PNG-bytes", "filename": "front.png"}]


class _ChunkOnlyStream(BytesIO):
    """Fails if anything reads the whole source at once."""

    def read(self, size=-1):
        if size is None or size < 0:
            raise AssertionError("source was read into memory whole")
        return super().read(size)


def _submit(monkeypatch, blobs, content):
    queued = []

    class Connection:
        def execute(self, sql, _params):
            if "'{current_ingest_job_id}'" in sql:
                return None
            return SimpleNamespace(fetchone=lambda: ("",))

    @contextmanager
    def unit_of_work(_database):
        yield SimpleNamespace(
            connection=Connection(), commit=lambda: None,
            assets=SimpleNamespace(create=lambda *_args: None),
            jobs=SimpleNamespace(create_job=lambda _context, job: queued.append(job)),
        )

    monkeypatch.setattr("app.apps.audiobook.service.unit_of_work", unit_of_work)
    monkeypatch.setattr("app.apps.audiobook.service.PostgresAudiobookRepository.get_project",
                        lambda *_args: {"id": "book"})
    service = AudiobookService(None, blobs)
    result = service.submit_source(
        SimpleNamespace(workspace_id="workspace"), project_id="book",
        source_format="txt", content=content, filename="book.txt",
    )
    return result, queued


def test_a_streamed_source_is_stored_in_bounded_reads(tmp_path, monkeypatch):
    blobs = LocalBlobStore(tmp_path)
    content = b"A long manuscript. " * 200_000

    result, queued = _submit(monkeypatch, blobs, _ChunkOnlyStream(content))

    assert queued[0]["input_payload"]["source_asset_id"] == result["source_asset_id"]
    stored = list(tmp_path.rglob("*-*"))
    assert [path.read_bytes() for path in stored if path.is_file()] == [content]


def test_a_source_that_changes_while_stored_is_refused(tmp_path, monkeypatch):
    class ChangingBlobs(LocalBlobStore):
        def put_stream(self, storage_key, stream, **kwargs):
            return super().put_stream(storage_key, BytesIO(b"edited meanwhile"), **kwargs)

    blobs = ChangingBlobs(tmp_path)
    with pytest.raises(UnsupportedSource, match="changed while it was being stored"):
        _submit(monkeypatch, blobs, BytesIO(b"original text"))
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
