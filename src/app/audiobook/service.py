"""Application service for durable projects and asynchronous source ingestion."""
from __future__ import annotations

from uuid import uuid4
from pathlib import Path
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.assets.canonical_voice_clones import discover_canonical_voice_clone_assets

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .extraction import MAX_SOURCE_BYTES, UnsupportedSource
from .analysis_repository import PostgresAudiobookAnalysisRepository
from .hashing import bytes_hash
from .repository import PostgresAudiobookRepository
from .review_repository import PostgresAudiobookReviewRepository
from .render_planner import load_chapter_units
from .export_service import start_export as create_export_job
from .report import audit_export


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

    @staticmethod
    def list_voices() -> list[dict[str, str]]:
        return [{"id": item.id,
                 "name": str(item.metadata.get("profile_name") or item.metadata.get("speaker") or item.id),
                 "language": str(item.metadata.get("language") or "")}
                for item in discover_canonical_voice_clone_assets() if item.storage_path]

    def get_project(self, context: TenantContext, project_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            repository = PostgresAudiobookRepository(work.connection)
            project = repository.get_project(context, project_id)
            if project is None:
                raise KeyError(project_id)
            cover_row = work.connection.execute(
                "SELECT cover_asset_id FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, project_id),
            ).fetchone()
            project["cover_asset_id"] = str(cover_row[0]) if cover_row and cover_row[0] else None
            chapters = repository.list_chapters(context, project["current_source_revision_id"]) if project["current_source_revision_id"] else []
            for chapter in chapters:
                chapter["spans"] = repository.list_spans(context, chapter["id"])
            project["review_issues"] = PostgresAudiobookAnalysisRepository(work.connection).list_review_issues(context, project_id)
            project["speakers"] = PostgresAudiobookReviewRepository(work.connection).list_speakers(context, project_id)
            pronunciation_rows = work.connection.execute(
                """SELECT DISTINCT ON (source_term) source_term, spoken_term, revision
                     FROM omnix_audiobook_pronunciations
                    WHERE workspace_id = %s AND project_id = %s
                    ORDER BY source_term, revision DESC""",
                (context.workspace_id, project_id),
            ).fetchall()
            project["pronunciations"] = [
                {"source_term": row[0], "spoken_term": row[1], "revision": row[2]}
                for row in pronunciation_rows
            ]
            run_row = work.connection.execute(
                "SELECT settings->>'current_render_run_id' FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, project_id),
            ).fetchone()
            render_run_id = str(run_row[0]) if run_row and run_row[0] else None
            if render_run_id:
                job_rows = work.connection.execute(
                    """
                    SELECT id, status, progress, error, attempt_count, max_attempts,
                           input_payload->>'chapter_id'
                      FROM omnix_jobs
                     WHERE workspace_id = %s AND module = 'audiobook'
                       AND job_type = 'audiobook.render-chapter'
                       AND input_payload->>'render_run_id' = %s
                     ORDER BY created_at, id
                    """, (context.workspace_id, render_run_id),
                ).fetchall()
                project["render_jobs"] = [
                    {"id": str(row[0]), "status": str(row[1]),
                     "progress": dict(row[2] or {}), "error": dict(row[3]) if row[3] else None,
                     "attempts": int(row[4]), "max_attempts": int(row[5]),
                     "chapter_id": str(row[6])}
                    for row in job_rows
                ]
                counts = work.connection.execute(
                    """
                    SELECT COALESCE(sum(jsonb_array_length(b.desired_keys)), 0),
                           COALESCE(sum(jsonb_array_length(b.completed_keys)), 0)
                      FROM omnix_audiobook_render_batches AS b
                      JOIN omnix_jobs AS j ON j.id = b.job_id AND j.workspace_id = b.workspace_id
                     WHERE b.workspace_id = %s AND j.input_payload->>'render_run_id' = %s
                    """, (context.workspace_id, render_run_id),
                ).fetchone()
                project["render_progress"] = {"total": int(counts[0]), "completed": int(counts[1])}
            else:
                project["render_jobs"] = []
                project["render_progress"] = {"total": 0, "completed": 0}
            export_rows = work.connection.execute(
                """SELECT j.id, j.status, j.progress, j.error,
                          m.format, m.id, m.manifest_hash
                     FROM omnix_audiobook_export_manifests m
                     JOIN omnix_jobs j ON j.id = m.job_id AND j.workspace_id = m.workspace_id
                    WHERE m.workspace_id = %s AND m.project_id = %s
                    ORDER BY m.created_at DESC LIMIT 20""",
                (context.workspace_id, project_id),
            ).fetchall()
            project["export_jobs"] = [
                {"id": row[0], "status": row[1], "progress": row[2],
                 "error": row[3], "format": row[4], "manifest_id": row[5],
                "manifest_hash": row[6]} for row in export_rows
            ]
            preview_rows = work.connection.execute(
                """SELECT id, status, progress, error, input_payload->>'span_id',
                          output_refs
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.preview-span'
                      AND input_payload->>'project_id' = %s
                    ORDER BY created_at DESC LIMIT 40""",
                (context.workspace_id, project_id),
            ).fetchall()
            project["preview_jobs"] = [
                {"id": row[0], "status": row[1], "progress": row[2],
                 "error": row[3], "span_id": row[4], "output_refs": row[5]}
                for row in preview_rows
            ]
            work.rollback()
        return {**project, "chapters": chapters}

    def add_speaker(self, context: TenantContext, *, project_id: str, canonical_name: str) -> dict[str, str]:
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookReviewRepository(work.connection).add_speaker(
                context, project_id=project_id, canonical_name=canonical_name,
            )
            work.commit()
        return result

    def set_pronunciation(
        self, context: TenantContext, *, project_id: str,
        source_term: str, spoken_term: str,
    ) -> dict[str, object]:
        term, spoken = source_term.strip(), spoken_term.strip()
        if not term or not spoken or len(term) > 128 or len(spoken) > 256:
            raise ValueError("pronunciation terms must be non-empty and within length limits")
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT state, settings->>'current_render_run_id'
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            current = work.connection.execute(
                """SELECT revision, spoken_term FROM omnix_audiobook_pronunciations
                    WHERE workspace_id = %s AND project_id = %s AND source_term = %s
                    ORDER BY revision DESC LIMIT 1""",
                (context.workspace_id, project_id, term),
            ).fetchone()
            if current and current[1] == spoken:
                return {"source_term": term, "spoken_term": spoken, "revision": int(current[0])}
            revision = int(current[0]) + 1 if current else 1
            from .hashing import canonical_json

            work.connection.execute(
                """INSERT INTO omnix_audiobook_pronunciations
                    (id, workspace_id, project_id, revision, source_term,
                     spoken_term, settings)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
                (f"ab:pron:{uuid4().hex}", context.workspace_id, project_id,
                 revision, term, spoken,
                 canonical_json({"confirmed_by_user_id": context.user_id})),
            )
            if project[1]:
                rows = work.connection.execute(
                    """SELECT id FROM omnix_jobs
                        WHERE workspace_id = %s AND module = 'audiobook'
                          AND job_type IN ('audiobook.render-chapter', 'audiobook.assemble-chapter')
                          AND input_payload->>'render_run_id' = %s
                          AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running')""",
                    (context.workspace_id, project[1]),
                ).fetchall()
                for (job_id,) in rows:
                    work.jobs.request_cancel(context, str(job_id))
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET state = CASE WHEN state IN ('rendering', 'mastering', 'rendered',
                                                    'ready_to_export', 'exported')
                                       THEN 'ready_to_render' ELSE state END,
                          settings = settings - 'current_render_run_id',
                          settings_revision = settings_revision + 1,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, project_id),
            )
            work.commit()
        return {"source_term": term, "spoken_term": spoken, "revision": revision}

    def set_cover(self, context: TenantContext, *, project_id: str,
                  content: bytes, filename: str = "cover") -> dict[str, str]:
        if not content or len(content) > 10 * 1024 * 1024:
            raise ValueError("cover must be non-empty and at most 10 MB")
        if content.startswith(b"\xff\xd8\xff"):
            mime, suffix = "image/jpeg", "jpg"
        elif content.startswith(b"\x89PNG\r\n\x1a\n"):
            mime, suffix = "image/png", "png"
        else:
            raise ValueError("cover must be a JPEG or PNG image")
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != ("JPEG" if suffix == "jpg" else "PNG"):
                    raise ValueError("cover format does not match its content")
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("cover image is corrupt") from exc
        asset_id = f"ab:cover:{uuid4().hex}"
        storage_key = f"audiobook/cover/{uuid4().hex}.{suffix}"
        blob = self.blobs.put_bytes(storage_key, content)
        try:
            with unit_of_work(self.database) as work:
                project = work.connection.execute(
                    """SELECT id FROM omnix_audiobook_projects
                        WHERE workspace_id = %s AND id = %s FOR UPDATE""",
                    (context.workspace_id, project_id),
                ).fetchone()
                if project is None:
                    raise KeyError(project_id)
                work.assets.create(context, {
                    "id": asset_id, "module": "audiobook", "asset_type": "cover",
                    "mime_type": mime, "byte_size": blob["byte_size"],
                    "checksum_sha256": blob["checksum_sha256"],
                    "storage_provider": blob["storage_provider"], "storage_key": storage_key,
                    "metadata": {"filename": filename},
                })
                work.connection.execute(
                    """UPDATE omnix_audiobook_projects
                          SET cover_asset_id = %s,
                              state = CASE WHEN state = 'exported' THEN 'ready_to_export' ELSE state END,
                              settings_revision = settings_revision + 1,
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    (asset_id, context.workspace_id, project_id),
                )
                work.commit()
        except Exception:
            if blob["created"]:
                self.blobs.delete(storage_key)
            raise
        return {"cover_asset_id": asset_id, "mime_type": mime}

    def confirm_alias(self, context: TenantContext, *, project_id: str,
                      speaker_id: str, alias: str) -> dict[str, str]:
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookReviewRepository(work.connection).confirm_alias(
                context, project_id=project_id, speaker_id=speaker_id, alias=alias,
            )
            work.commit()
        return result

    def assign_voice(
        self, context: TenantContext, *, project_id: str,
        speaker_id: str, voice_profile_id: str,
    ) -> dict[str, object]:
        profile = next((item for item in discover_canonical_voice_clone_assets()
                        if item.id == voice_profile_id), None)
        if profile is None or not profile.storage_path:
            raise ValueError("voice profile is unavailable")
        voice_hash = bytes_hash(Path(profile.storage_path).read_bytes())
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookReviewRepository(work.connection).assign_voice(
                context, project_id=project_id, speaker_id=speaker_id,
                voice_profile_id=voice_profile_id, voice_revision_hash=voice_hash,
            )
            work.commit()
        return result

    def resolve_issue(
        self, context: TenantContext, *, project_id: str,
        issue_id: str, speaker_id: str, role: str, delivery: str = "",
    ) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookReviewRepository(work.connection).resolve_issue(
                context, project_id=project_id, issue_id=issue_id,
                speaker_id=speaker_id, role=role, delivery=delivery,
            )
            work.commit()
        return result

    def start_render(
        self, context: TenantContext, *, project_id: str,
        provider_id: str = "faster-qwen3-tts", model_id: str = "Qwen3-TTS",
        model_revision: str, generation_parameters: dict[str, object] | None = None,
        seed: int | None = None,
    ) -> dict[str, object]:
        if not model_revision.strip():
            raise ValueError("a pinned model revision is required for reproducible rendering")
        if seed is not None or "seed" in (generation_parameters or {}):
            raise ValueError("this TTS provider does not apply generation seeds")
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """
                SELECT current_source_revision_id, state FROM omnix_audiobook_projects
                 WHERE workspace_id = %s AND id = %s FOR UPDATE
                """, (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            if project[1] == "rendering":
                active = int(work.connection.execute(
                    """
                    SELECT count(*) FROM omnix_jobs
                     WHERE workspace_id = %s AND module = 'audiobook'
                       AND job_type = 'audiobook.render-chapter'
                       AND input_payload->>'project_id' = %s
                       AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running', 'cancel_requested')
                    """, (context.workspace_id, project_id),
                ).fetchone()[0])
                if active:
                    raise ValueError("project is already rendering")
            elif project[1] != "ready_to_render":
                raise ValueError("project has unresolved review work")
            if not project[0]:
                raise ValueError("project has no canonical source")
            chapters = PostgresAudiobookRepository(work.connection).list_chapters(context, str(project[0]))
            if not chapters:
                raise ValueError("project has no canonical chapters")
            for chapter in chapters:
                load_chapter_units(work.connection, context, project_id=project_id, chapter_id=chapter["id"])
            jobs = []
            render_run_id = f"ab:run:{uuid4().hex}"
            for chapter in chapters:
                job_id = f"ab:job:{uuid4().hex}"
                work.jobs.create_job(context, {
                    "id": job_id, "module": "audiobook", "job_type": "audiobook.render-chapter",
                    "resource_class": "gpu:tts:offline", "priority": -100,
                    "input_payload": {"project_id": project_id,
                                      "render_run_id": render_run_id,
                                      "source_revision_id": str(project[0]),
                                      "chapter_id": chapter["id"],
                                      "provider_id": provider_id, "model_id": model_id,
                                      "model_revision": model_revision,
                                      "generation_parameters": generation_parameters or {},
                                      "seed": seed},
                    "max_attempts": 5,
                })
                jobs.append(job_id)
            work.connection.execute(
                """
                UPDATE omnix_audiobook_projects
                   SET state = 'rendering',
                       settings = jsonb_set(settings, '{current_render_run_id}', to_jsonb(%s::text), true),
                       settings_revision = settings_revision + 1,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE workspace_id = %s AND id = %s
                """, (render_run_id, context.workspace_id, project_id),
            )
            work.commit()
        return {"project_id": project_id, "render_run_id": render_run_id,
                "job_ids": jobs, "chapter_count": len(chapters)}

    def start_preview(
        self, context: TenantContext, *, project_id: str,
        chapter_id: str, span_id: str, model_revision: str,
        provider_id: str = "faster-qwen3-tts", model_id: str = "Qwen3-TTS",
        generation_parameters: dict[str, object] | None = None,
        seed: int | None = None,
    ) -> dict[str, str]:
        if not model_revision.strip():
            raise ValueError("a pinned model revision is required")
        if seed is not None or "seed" in (generation_parameters or {}):
            raise ValueError("this TTS provider does not apply generation seeds")
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT current_source_revision_id FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            chapter = work.connection.execute(
                """SELECT id FROM omnix_audiobook_chapters
                    WHERE workspace_id = %s AND id = %s AND source_revision_id = %s""",
                (context.workspace_id, chapter_id, project[0]),
            ).fetchone()
            if chapter is None:
                raise ValueError("chapter is not in the current source")
            units = load_chapter_units(work.connection, context, project_id=project_id,
                                       chapter_id=chapter_id)
            if not any(unit.span_id == span_id for unit in units):
                raise ValueError("span is not renderable in this chapter")
            job_id = f"ab:preview:{uuid4().hex}"
            work.jobs.create_job(context, {
                "id": job_id, "module": "audiobook", "job_type": "audiobook.preview-span",
                "resource_class": "gpu:tts:preview", "priority": 50,
                "input_payload": {"project_id": project_id, "chapter_id": chapter_id,
                                  "source_revision_id": str(project[0]), "span_id": span_id,
                                  "provider_id": provider_id, "model_id": model_id,
                                  "model_revision": model_revision,
                                  "generation_parameters": generation_parameters or {},
                                  "seed": seed},
                "max_attempts": 3,
            })
            work.commit()
        return {"job_id": job_id, "span_id": span_id}

    def read_preview(self, context: TenantContext, *, project_id: str,
                     job_id: str) -> bytes:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """SELECT a.storage_key, a.checksum_sha256
                     FROM omnix_jobs j
                     JOIN omnix_audiobook_renders r
                       ON r.id = j.output_refs->0->>'render_id'
                      AND r.workspace_id = j.workspace_id
                     JOIN omnix_assets a
                       ON a.id = r.audio_asset_id AND a.workspace_id = r.workspace_id
                    WHERE j.workspace_id = %s AND j.id = %s
                      AND j.module = 'audiobook' AND j.job_type = 'audiobook.preview-span'
                      AND j.status = 'completed'
                      AND j.input_payload->>'project_id' = %s
                      AND r.audio_asset_id = j.output_refs->0->>'audio_asset_id'
                      AND a.module = 'audiobook' AND a.lifecycle_status = 'active'
                      AND a.checksum_sha256 = r.audio_checksum""",
                (context.workspace_id, job_id, project_id),
            ).fetchone()
            work.rollback()
        if row is None:
            raise KeyError(job_id)
        return self.blobs.read_bytes(str(row[0]), expected_checksum=str(row[1]))

    def start_export(self, context: TenantContext, *, project_id: str,
                     format: str = "m4b") -> dict[str, str]:
        return create_export_job(self.database, self.blobs, context,
                                 project_id=project_id, format=format)

    def list_exports(self, context: TenantContext, project_id: str) -> list[dict[str, object]]:
        with unit_of_work(self.database) as work:
            rows = work.connection.execute(
                """SELECT e.id, e.format, e.manifest_hash, e.output_asset_id,
                          e.created_at, a.byte_size
                     FROM omnix_audiobook_exports e
                     JOIN omnix_assets a ON a.id = e.output_asset_id
                    WHERE e.workspace_id = %s AND e.project_id = %s
                    ORDER BY e.created_at DESC""",
                (context.workspace_id, project_id),
            ).fetchall()
            work.rollback()
        return [{"id": row[0], "format": row[1], "manifest_hash": row[2],
                 "asset_id": row[3], "created_at": row[4].isoformat(),
                 "byte_size": row[5]} for row in rows]

    def read_export(self, context: TenantContext, *, project_id: str,
                    export_id: str) -> tuple[bytes, str, str]:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """SELECT e.format, a.storage_key, a.checksum_sha256
                     FROM omnix_audiobook_exports e
                     JOIN omnix_assets a ON a.id = e.output_asset_id
                    WHERE e.workspace_id = %s AND e.project_id = %s AND e.id = %s
                      AND a.lifecycle_status = 'active'""",
                (context.workspace_id, project_id, export_id),
            ).fetchone()
            work.rollback()
        if row is None:
            raise KeyError(export_id)
        from .export import FORMAT_MIME

        return (self.blobs.read_bytes(str(row[1]), expected_checksum=str(row[2])),
                FORMAT_MIME[str(row[0])], str(row[0]))

    def export_report(self, context: TenantContext, *, project_id: str,
                      export_id: str) -> dict[str, object]:
        return audit_export(self.database, self.blobs, context,
                            project_id=project_id, export_id=export_id)

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
