"""Application service for durable projects and asynchronous source ingestion."""
from __future__ import annotations

from uuid import uuid4

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .extraction import MAX_SOURCE_BYTES, UnsupportedSource
from .hashing import bytes_hash
from .repository import PostgresAudiobookRepository


_MIME = {"epub": "application/epub+zip", "txt": "text/plain; charset=utf-8", "md": "text/markdown; charset=utf-8"}


class AudiobookService:
    def __init__(self, database: PostgresDatabase, blobs: LocalBlobStore) -> None:
        self.database = database
        self.blobs = blobs

    def create_project(
        self, context: TenantContext, *, title: str, author: str = "", language: str = "en",
    ) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookRepository(work.connection).create_project(
                context, project_id=f"ab:pr:{uuid4().hex}", title=title,
                author=author, language=language,
            )
            work.commit()
        return result

    def list_projects(self, context: TenantContext) -> list[dict[str, object]]:
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookRepository(work.connection).list_projects(context)
            work.rollback()
        return result

    def get_project(self, context: TenantContext, project_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            repository = PostgresAudiobookRepository(work.connection)
            project = repository.get_project(context, project_id)
            if project is None:
                raise KeyError(project_id)
            chapters = repository.list_chapters(context, project["current_source_revision_id"]) if project["current_source_revision_id"] else []
            for chapter in chapters:
                chapter["spans"] = repository.list_spans(context, chapter["id"])
            work.rollback()
        return {**project, "chapters": chapters}

    def submit_source(
        self, context: TenantContext, *, project_id: str,
        source_format: str, content: bytes, filename: str,
    ) -> dict[str, str]:
        if source_format not in _MIME:
            raise UnsupportedSource(f"unsupported source format: {source_format}")
        if not content or len(content) > MAX_SOURCE_BYTES:
            raise UnsupportedSource("source is empty or exceeds the supported size limit")
        source_hash = bytes_hash(content)
        asset_id = f"ab:source:{uuid4().hex}"
        storage_key = f"audiobook/source/{asset_id.split(':')[-1]}-{source_hash}"
        job_id = f"ab:job:{uuid4().hex}"
        blob = self.blobs.put_bytes(storage_key, content)
        try:
            with unit_of_work(self.database) as work:
                repository = PostgresAudiobookRepository(work.connection)
                if repository.get_project(context, project_id) is None:
                    raise KeyError(project_id)
                work.assets.create(context, {
                    "id": asset_id, "module": "audiobook", "asset_type": "source",
                    "mime_type": _MIME[source_format], "byte_size": blob["byte_size"],
                    "checksum_sha256": blob["checksum_sha256"],
                    "storage_provider": blob["storage_provider"], "storage_key": storage_key,
                    "metadata": {"filename": filename, "source_format": source_format},
                })
                work.jobs.create_job(context, {
                    "id": job_id, "module": "audiobook", "job_type": "audiobook.ingest",
                    "resource_class": "cpu", "priority": 0,
                    "input_payload": {"project_id": project_id, "source_asset_id": asset_id,
                                      "source_format": source_format},
                    "max_attempts": 3,
                })
                work.commit()
        except Exception:
            if blob["created"]:
                self.blobs.delete(storage_key)
            raise
        return {"project_id": project_id, "source_asset_id": asset_id, "job_id": job_id}
