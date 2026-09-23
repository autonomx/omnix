"""Application service for durable projects and asynchronous source ingestion."""
from __future__ import annotations

from uuid import uuid4
from pathlib import Path
from io import BytesIO
from typing import Any, BinaryIO

from PIL import Image, UnidentifiedImageError

from app.assets.canonical_voice_clones import discover_canonical_voice_clone_assets

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .extraction import (
    EXTRACTOR_VERSION,
    MAX_SOURCE_BYTES,
    SUPPORTED_SOURCE_FORMATS,
    UnsupportedSource,
    normalize_extraction_settings,
)
from .spans import DETECTOR_VERSION
from .analysis_repository import PostgresAudiobookAnalysisRepository
from .hashing import bytes_hash
from .repository import PostgresAudiobookRepository
from .review_repository import PostgresAudiobookReviewRepository
from .render_planner import load_chapter_units
from .export_service import start_export as create_export_job
from .report import audit_export
from .model_identity import assert_model_revision
from .document_structure import (
    ANALYSIS_POLICY_VERSION, DOCUMENT_STRUCTURE_VERSION, RENDER_POLICY_VERSION,
    analysis_policy, effective_render_action, effective_role,
)
from .document_structure_repository import PostgresAudiobookDocumentStructureRepository


WORDS_PER_MINUTE = 150.0

_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "epub": "application/epub+zip",
    "html": "text/html; charset=utf-8",
    "htm": "text/html; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "pdf": "application/pdf",
    "text": "text/plain; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}

if set(_MIME) != set(SUPPORTED_SOURCE_FORMATS):  # pragma: no cover - developer contract
    raise RuntimeError("audiobook source format MIME mappings are incomplete")


class AudiobookService:
    def __init__(self, database: PostgresDatabase, blobs: LocalBlobStore) -> None:
        self.database = database
        self.blobs = blobs

    @staticmethod
    def _require_active_project(connection: Any, context: TenantContext,
                                project_id: str, *, lock: bool = False) -> None:
        locking = " FOR UPDATE" if lock else ""
        row = connection.execute(
            "SELECT 1 FROM omnix_audiobook_projects "
            "WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL" + locking,
            (context.workspace_id, project_id),
        ).fetchone()
        if row is None:
            raise KeyError(project_id)

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

    def update_project(
        self, context: TenantContext, *, project_id: str,
        title: str, author: str = "",
    ) -> dict[str, object]:
        title = title.strip()
        author = author.strip()
        if not title:
            raise ValueError("title is required")
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET title = %s, author = %s,
                          state = CASE WHEN state = 'exported'
                                       THEN 'ready_to_export' ELSE state END,
                          settings_revision = settings_revision + 1,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s
                      AND deleted_at IS NULL
                    RETURNING id, title, author, language, state,
                              current_source_revision_id""",
                (title, author, context.workspace_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError(project_id)
            work.commit()
        return {
            "id": str(row[0]), "title": str(row[1]), "author": str(row[2]),
            "language": str(row[3]), "state": str(row[4]),
            "current_source_revision_id": str(row[5]) if row[5] else None,
        }

    def delete_project(self, context: TenantContext, *, project_id: str) -> None:
        """Hide a project while retaining immutable source and production history."""
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT id FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                    FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            jobs = work.connection.execute(
                """SELECT id FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND input_payload->>'project_id' = %s
                      AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running')""",
                (context.workspace_id, project_id),
            ).fetchall()
            for (job_id,) in jobs:
                work.jobs.request_cancel(context, str(job_id))
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET deleted_at = CURRENT_TIMESTAMP,
                          current_source_revision_id = NULL,
                          state = 'deleted',
                          settings = settings - 'current_render_run_id',
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL""",
                (context.workspace_id, project_id),
            )
            work.commit()

    def list_projects(self, context: TenantContext, *, offset: int = 0) -> list[dict[str, object]]:
        with unit_of_work(self.database) as work:
            result = PostgresAudiobookRepository(work.connection).list_projects(context, offset=offset)
            work.rollback()
        return result

    @staticmethod
    def list_voices() -> list[dict[str, str]]:
        return [{"id": item.id,
                 "name": str(item.metadata.get("profile_name") or item.metadata.get("speaker") or item.id),
                 "language": str(item.metadata.get("language") or "")}
                for item in discover_canonical_voice_clone_assets() if item.storage_path]

    def get_project(self, context: TenantContext, project_id: str, *,
                    include_text: bool = True) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            repository = PostgresAudiobookRepository(work.connection)
            project = repository.get_project(context, project_id)
            if project is None:
                raise KeyError(project_id)
            cover_row = work.connection.execute(
                """SELECT cover_asset_id, settings
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, project_id),
            ).fetchone()
            project["cover_asset_id"] = str(cover_row[0]) if cover_row and cover_row[0] else None
            project_settings = dict(cover_row[1] or {}) if cover_row else {}
            project["audiobook_mode"] = str(
                project_settings.get("audiobook_mode") or "standard"
            )
            project["document_structure_version"] = DOCUMENT_STRUCTURE_VERSION
            project["render_policy_version"] = RENDER_POLICY_VERSION
            project["analysis_policy_version"] = ANALYSIS_POLICY_VERSION
            source_row = work.connection.execute(
                """SELECT r.source_format, a.metadata->>'filename', a.byte_size
                     FROM omnix_audiobook_projects p
                     LEFT JOIN omnix_audiobook_source_revisions r
                       ON r.workspace_id = p.workspace_id
                      AND r.id = p.current_source_revision_id
                     JOIN omnix_assets a
                       ON a.workspace_id = r.workspace_id
                      AND a.id = r.original_asset_id
                    WHERE p.workspace_id = %s AND p.id = %s
                      AND a.lifecycle_status = 'active'""",
                (context.workspace_id, project_id),
            ).fetchone()
            project["source_format"] = str(source_row[0]) if source_row else None
            project["source_filename"] = str(source_row[1]) if source_row and source_row[1] else None
            project["source_size_bytes"] = int(source_row[2]) if source_row and source_row[2] is not None else 0
            if project["current_source_revision_id"] and include_text:
                chapters = repository.list_chapters(context, project["current_source_revision_id"])
                for chapter in chapters:
                    chapter["spans"] = repository.list_spans(context, chapter["id"])
                    chapter["span_count"] = len(chapter["spans"])
            elif project["current_source_revision_id"]:
                chapter_rows = work.connection.execute(
                    """SELECT id, ordinal, title, canonical_hash,
                              length(canonical_text),
                              (SELECT count(*) FROM omnix_audiobook_spans s
                                WHERE s.workspace_id = c.workspace_id
                                  AND s.chapter_id = c.id)
                         FROM omnix_audiobook_chapters AS c
                        WHERE c.workspace_id = %s AND c.source_revision_id = %s
                        ORDER BY ordinal""",
                    (context.workspace_id, project["current_source_revision_id"]),
                ).fetchall()
                chapters = [{"id": str(row[0]), "ordinal": int(row[1]),
                             "title": str(row[2]), "canonical_hash": str(row[3]),
                             "character_count": int(row[4]), "span_count": int(row[5])}
                            for row in chapter_rows]
            else:
                chapters = []
            project["review_issues"] = (
                PostgresAudiobookAnalysisRepository(work.connection).list_review_issues(
                    context, project_id,
                ) if project["state"] not in {"extracted", "ingesting"} else []
            )
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
            pipeline_rows = work.connection.execute(
                """SELECT id, job_type, status, progress, error,
                          attempt_count, max_attempts,
                          input_payload->>'chapter_id', metadata
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type IN ('audiobook.ingest', 'audiobook.analyze',
                                       'audiobook.assemble-chapter')
                      AND input_payload->>'project_id' = %s
                    ORDER BY created_at DESC LIMIT 30""",
                (context.workspace_id, project_id),
            ).fetchall()
            project["pipeline_jobs"] = [
                {"id": str(row[0]), "type": str(row[1]), "status": str(row[2]),
                 "progress": dict(row[3] or {}),
                 "error": dict(row[4]) if row[4] else None,
                 "attempts": int(row[5]), "max_attempts": int(row[6]),
                 "chapter_id": str(row[7]) if row[7] else None,
                 "can_retry": (str(row[2]) in {"failed", "canceled", "stale"}
                               and not dict(row[8] or {}).get("superseded_by")),
                 "superseded_by": dict(row[8] or {}).get("superseded_by"),
                 "reason": dict(row[8] or {}).get("reason"),
                 "migration": dict(row[8] or {}).get("migration"),
                 "pause_requested": bool(dict(row[8] or {}).get("pause_requested")),
                 "paused": bool(dict(row[8] or {}).get("paused"))}
                for row in pipeline_rows
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
                     "chapter_id": str(row[6]),
                     "can_retry": bool((dict(row[3] or {}).get("retryable", True))
                                       and int(row[4]) < int(row[5]))}
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
            if project["current_source_revision_id"]:
                text_rows = work.connection.execute(
                    """SELECT canonical_text
                         FROM omnix_audiobook_chapters
                        WHERE workspace_id = %s AND source_revision_id = %s
                        ORDER BY ordinal""",
                    (context.workspace_id, project["current_source_revision_id"]),
                ).fetchall()
                for chapter, row in zip(chapters, text_rows):
                    chapter["word_count"] = len(str(row[0]).split())
                    chapter["estimated_runtime_seconds"] = (chapter["word_count"] / WORDS_PER_MINUTE) * 60.0
                word_count = sum(chapter["word_count"] for chapter in chapters)
                runtime_row = work.connection.execute(
                    """SELECT COALESCE(sum(latest.duration_seconds), 0)
                         FROM omnix_audiobook_chapters AS ch
                         LEFT JOIN LATERAL (
                             SELECT duration_seconds
                               FROM omnix_audiobook_chapter_assemblies
                              WHERE workspace_id = ch.workspace_id
                                AND chapter_id = ch.id
                              ORDER BY created_at DESC LIMIT 1
                         ) AS latest ON TRUE
                        WHERE ch.workspace_id = %s AND ch.source_revision_id = %s""",
                    (context.workspace_id, project["current_source_revision_id"]),
                ).fetchone()
                project["word_count"] = word_count
                project["estimated_runtime_seconds"] = (word_count / WORDS_PER_MINUTE) * 60.0
                project["actual_runtime_seconds"] = float(runtime_row[0] or 0.0)
            else:
                project["word_count"] = 0
                project["estimated_runtime_seconds"] = 0.0
                project["actual_runtime_seconds"] = 0.0
            work.rollback()
        return {**project, "chapters": chapters}

    def get_chapter(self, context: TenantContext, *, project_id: str,
                    chapter_id: str) -> dict[str, object]:
        from dataclasses import asdict

        from .speech_plan import build_speech_plan

        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """SELECT c.id, c.ordinal, c.title, c.canonical_text, c.canonical_hash,
                          c.source_revision_id, p.state, p.settings
                     FROM omnix_audiobook_chapters c
                     JOIN omnix_audiobook_projects p
                       ON p.workspace_id = c.workspace_id
                      AND p.current_source_revision_id = c.source_revision_id
                    WHERE c.workspace_id = %s AND p.id = %s AND c.id = %s
                      AND p.deleted_at IS NULL""",
                (context.workspace_id, project_id, chapter_id),
            ).fetchone()
            if row is None:
                raise KeyError(chapter_id)
            spans = PostgresAudiobookRepository(work.connection).list_spans(context, chapter_id)
            annotation_rows = work.connection.execute(
                """SELECT s.id, a.id, a.revision, a.role, a.speaker_id,
                          a.speaker_candidate, a.delivery, a.evidence, a.review_status
                     FROM omnix_audiobook_spans s
                     LEFT JOIN LATERAL (
                         SELECT id, revision, role, speaker_id, speaker_candidate,
                                delivery, evidence, review_status
                           FROM omnix_audiobook_annotations
                          WHERE workspace_id = s.workspace_id AND span_id = s.id
                          ORDER BY revision DESC LIMIT 1
                     ) a ON TRUE
                    WHERE s.workspace_id = %s AND s.chapter_id = %s
                    ORDER BY s.ordinal""",
                (context.workspace_id, chapter_id),
            ).fetchall() if row[6] not in {"extracted", "ingesting"} else []
            annotations = {
                str(item[0]): {"id": str(item[1]), "revision": int(item[2]),
                               "role": str(item[3]),
                               "speaker_id": str(item[4]) if item[4] else None,
                               "speaker_candidate": str(item[5]) if item[5] else None,
                               "delivery": str(item[6]), "evidence": dict(item[7]),
                               "review_status": str(item[8])}
                for item in annotation_rows if item[1] is not None
            }
            pronunciation_rows = work.connection.execute(
                """SELECT DISTINCT ON (source_term) source_term, spoken_term
                     FROM omnix_audiobook_pronunciations
                    WHERE workspace_id = %s AND project_id = %s
                    ORDER BY source_term, revision DESC""",
                (context.workspace_id, project_id),
            ).fetchall()
            overrides = {str(term): str(spoken) for term, spoken in pronunciation_rows}
            structure_repository = PostgresAudiobookDocumentStructureRepository(
                work.connection
            )
            blocks = structure_repository.list_blocks(
                context, source_revision_id=str(row[5]), chapter_id=chapter_id,
            )
            document_overrides = structure_repository.list_overrides(
                context, project_id=project_id, source_revision_id=str(row[5]),
            )
            audiobook_mode = str(dict(row[7] or {}).get("audiobook_mode") or "standard")
            block_payload = []
            for block in blocks:
                payload = asdict(block)
                role = effective_role(block, document_overrides)
                payload["effective_role"] = role
                payload["render_action"] = effective_render_action(
                    block, mode=audiobook_mode, overrides=document_overrides,
                )
                payload["speaker_analysis_visibility"] = analysis_policy(
                    role, "speaker_attribution"
                )
                block_payload.append(payload)
            for span in spans:
                span["annotation"] = annotations.get(span["id"])
                plan = build_speech_plan(span["source_text"], overrides=overrides)
                span["speech_plan"] = {"tts_input_text": plan.tts_input_text,
                                       "hash": plan.hash,
                                       "transformations": [asdict(item) for item in plan.transformations]}
            work.rollback()
        return {"id": str(row[0]), "ordinal": int(row[1]), "title": str(row[2]),
                "canonical_text": str(row[3]), "canonical_hash": str(row[4]),
                "spans": spans, "document_blocks": block_payload,
                "audiobook_mode": audiobook_mode,
                "render_policy_version": RENDER_POLICY_VERSION,
                "analysis_policy_version": ANALYSIS_POLICY_VERSION}

    def get_document_structure(
        self, context: TenantContext, *, project_id: str,
        chapter_id: str | None = None,
    ) -> dict[str, object]:
        from dataclasses import asdict

        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT current_source_revision_id, settings
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            if not project[0]:
                return {
                    "source_revision_id": None, "run_id": None, "blocks": [],
                    "overrides": [], "audiobook_mode": "standard",
                }
            source_revision_id = str(project[0])
            repository = PostgresAudiobookDocumentStructureRepository(work.connection)
            blocks = repository.list_blocks(
                context, source_revision_id=source_revision_id,
                chapter_id=chapter_id,
            )
            overrides = repository.list_overrides(
                context, project_id=project_id,
                source_revision_id=source_revision_id,
            )
            mode = str(dict(project[1] or {}).get("audiobook_mode") or "standard")
            rendered = []
            for block in blocks:
                item = asdict(block)
                role = effective_role(block, overrides)
                item["effective_role"] = role
                item["render_action"] = effective_render_action(
                    block, mode=mode, overrides=overrides,
                )
                item["analysis_visibility"] = {
                    consumer: analysis_policy(role, consumer)
                    for consumer in (
                        "speaker_attribution", "chapter_summarizer",
                        "dialogue_pronunciation",
                    )
                }
                rendered.append(item)
            run_id = repository.latest_run_id(context, source_revision_id)
            work.rollback()
        return {
            "source_revision_id": source_revision_id,
            "run_id": run_id,
            "document_structure_version": DOCUMENT_STRUCTURE_VERSION,
            "render_policy_version": RENDER_POLICY_VERSION,
            "analysis_policy_version": ANALYSIS_POLICY_VERSION,
            "audiobook_mode": mode,
            "blocks": rendered,
            "overrides": overrides,
        }

    def set_audiobook_mode(
        self, context: TenantContext, *, project_id: str, mode: str,
    ) -> dict[str, object]:
        mode = mode.strip().casefold()
        if mode not in {"standard", "story_only", "verbatim"}:
            raise ValueError("audiobook mode must be standard, story_only, or verbatim")
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT state, settings->>'current_render_run_id'
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                    FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            if project[1]:
                rows = work.connection.execute(
                    """SELECT id FROM omnix_jobs
                        WHERE workspace_id = %s AND module = 'audiobook'
                          AND job_type IN ('audiobook.render-chapter',
                                           'audiobook.assemble-chapter')
                          AND input_payload->>'render_run_id' = %s
                          AND status IN ('queued', 'waiting', 'retrying', 'leased',
                                         'running', 'paused', 'cancel_requested')""",
                    (context.workspace_id, str(project[1])),
                ).fetchall()
                for (job_id,) in rows:
                    work.jobs.request_cancel(context, str(job_id))
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET settings = jsonb_set(
                              settings - 'current_render_run_id',
                              '{audiobook_mode}', to_jsonb(%s::text), true
                          ),
                          state = CASE
                              WHEN state IN ('rendering', 'mastering', 'rendered',
                                             'ready_to_export', 'exported')
                              THEN 'ready_to_render' ELSE state END,
                          settings_revision = settings_revision + 1,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                (mode, context.workspace_id, project_id),
            )
            work.commit()
        return {
            "project_id": project_id, "audiobook_mode": mode,
            "render_policy_version": RENDER_POLICY_VERSION,
        }

    def set_document_override(
        self, context: TenantContext, *, project_id: str, scope: str,
        scope_key: str, action: str = "DEFAULT",
        role_override: str | None = None,
    ) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT current_source_revision_id, state,
                          settings->>'current_render_run_id'
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                    FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            if not project[0]:
                raise ValueError("project has no canonical source")
            result = PostgresAudiobookDocumentStructureRepository(
                work.connection
            ).append_override(
                context, project_id=project_id,
                source_revision_id=str(project[0]), scope=scope,
                scope_key=scope_key, action=action,
                role_override=role_override,
            )
            if project[2]:
                rows = work.connection.execute(
                    """SELECT id FROM omnix_jobs
                        WHERE workspace_id = %s AND module = 'audiobook'
                          AND job_type IN ('audiobook.render-chapter',
                                           'audiobook.assemble-chapter')
                          AND input_payload->>'render_run_id' = %s
                          AND status IN ('queued', 'waiting', 'retrying', 'leased',
                                         'running', 'paused', 'cancel_requested')""",
                    (context.workspace_id, str(project[2])),
                ).fetchall()
                for (job_id,) in rows:
                    work.jobs.request_cancel(context, str(job_id))
            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET settings = settings - 'current_render_run_id',
                          state = CASE
                              WHEN state IN ('rendering', 'mastering', 'rendered',
                                             'ready_to_export', 'exported')
                              THEN 'ready_to_render' ELSE state END,
                          settings_revision = settings_revision + 1,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, project_id),
            )
            work.commit()
        return result

    def add_speaker(self, context: TenantContext, *, project_id: str, canonical_name: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
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
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE""",
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
                        WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE""",
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

    def read_cover(self, context: TenantContext, *, project_id: str) -> tuple[bytes, str]:
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """SELECT a.storage_key, a.checksum_sha256, a.mime_type
                     FROM omnix_audiobook_projects p
                     JOIN omnix_assets a ON a.workspace_id = p.workspace_id
                                        AND a.id = p.cover_asset_id
                    WHERE p.workspace_id = %s AND p.id = %s AND p.deleted_at IS NULL
                      AND a.lifecycle_status = 'active'""",
                (context.workspace_id, project_id),
            ).fetchone()
            work.rollback()
        if row is None:
            raise KeyError(project_id)
        return self.blobs.read_bytes(str(row[0]), expected_checksum=str(row[1])), str(row[2])

    def delete_asset(self, context: TenantContext, *, project_id: str,
                     asset_id: str) -> dict[str, object]:
        """Soft-delete a project asset and remove its local blob.

        Generated exports and the current cover are user-managed assets. Source
        assets remain immutable because they back the project's source revisions.
        """
        storage_key: str
        relationship: str
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT cover_asset_id
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                    FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)

            asset = work.connection.execute(
                """SELECT id, storage_key, revision, lifecycle_status
                     FROM omnix_assets
                    WHERE workspace_id = %s AND id = %s
                    FOR UPDATE""",
                (context.workspace_id, asset_id),
            ).fetchone()
            if asset is None or str(asset[3]) == "deleted":
                raise KeyError(asset_id)
            storage_key = str(asset[1])

            if project[0] is not None and str(project[0]) == asset_id:
                relationship = "cover"
            else:
                export = work.connection.execute(
                    """SELECT id
                         FROM omnix_audiobook_exports
                        WHERE workspace_id = %s AND project_id = %s
                          AND output_asset_id = %s""",
                    (context.workspace_id, project_id, asset_id),
                ).fetchone()
                if export is not None:
                    relationship = "export"
                else:
                    source = work.connection.execute(
                        """SELECT 1
                             FROM omnix_audiobook_source_revisions
                            WHERE workspace_id = %s AND project_id = %s
                              AND original_asset_id = %s
                            LIMIT 1""",
                        (context.workspace_id, project_id, asset_id),
                    ).fetchone()
                    if source is not None:
                        raise ValueError("the manuscript source cannot be deleted")
                    raise KeyError(asset_id)

            deleted = work.assets.mark_deleted(
                context, asset_id=asset_id, expected_revision=int(asset[2]),
            )
            if relationship == "cover":
                work.connection.execute(
                    """UPDATE omnix_audiobook_projects
                          SET cover_asset_id = NULL,
                              state = CASE WHEN state = 'exported'
                                           THEN 'ready_to_export' ELSE state END,
                              settings_revision = settings_revision + 1,
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    (context.workspace_id, project_id),
                )
            work.audit.append(
                context,
                aggregate_type="asset",
                aggregate_id=asset_id,
                action="asset.deleted",
                payload={"project_id": project_id, "relationship": relationship,
                         "revision": deleted["revision"], "delete_blob": True},
            )
            work.commit()

        return {"asset_id": asset_id, "deleted": True,
                "file_deleted": self.blobs.delete(storage_key)}

    def open_source(self, context: TenantContext, *, project_id: str) -> tuple[BinaryIO, str, str]:
        """Open the current immutable source revision for browser download."""
        with unit_of_work(self.database) as work:
            row = work.connection.execute(
                """SELECT a.storage_key, a.checksum_sha256, a.mime_type,
                          r.source_format, a.metadata->>'filename'
                     FROM omnix_audiobook_projects p
                     JOIN omnix_audiobook_source_revisions r
                       ON r.workspace_id = p.workspace_id
                      AND r.id = p.current_source_revision_id
                     JOIN omnix_assets a
                       ON a.workspace_id = r.workspace_id
                      AND a.id = r.original_asset_id
                    WHERE p.workspace_id = %s AND p.id = %s AND p.deleted_at IS NULL
                      AND a.lifecycle_status = 'active'""",
                (context.workspace_id, project_id),
            ).fetchone()
            work.rollback()
        if row is None:
            raise KeyError(project_id)
        source_format = str(row[3])
        filename = Path(str(row[4] or f"ebook.{source_format}")).name
        return (
            self.blobs.open_verified(str(row[0]), expected_checksum=str(row[1])),
            str(row[2]),
            filename or f"ebook.{source_format}",
        )

    def confirm_alias(self, context: TenantContext, *, project_id: str,
                      speaker_id: str, alias: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
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
            self._require_active_project(work.connection, context, project_id, lock=True)
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
            self._require_active_project(work.connection, context, project_id, lock=True)
            result = PostgresAudiobookReviewRepository(work.connection).resolve_issue(
                context, project_id=project_id, issue_id=issue_id,
                speaker_id=speaker_id, role=role, delivery=delivery,
            )
            work.commit()
        return result

    def revise_span(
        self, context: TenantContext, *, project_id: str, span_id: str,
        speaker_id: str, role: str, delivery: str = "",
    ) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            result = PostgresAudiobookReviewRepository(work.connection).revise_span(
                context, project_id=project_id, span_id=span_id,
                speaker_id=speaker_id, role=role, delivery=delivery,
            )
            work.commit()
        return result

    def cancel_job(self, context: TenantContext, *, project_id: str,
                   job_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            row = work.connection.execute(
                """SELECT status, job_type FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s AND module = 'audiobook'
                      AND input_payload->>'project_id' = %s
                    FOR UPDATE""",
                (context.workspace_id, job_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            # Analysis cancellation is safe to finalize immediately: the
            # worker's chapter writes and lease renewal share one transaction,
            # so clearing ownership prevents any partial commit while a
            # provider call is still unwinding. Render jobs retain their
            # cooperative cancel path because providers may have external
            # encoder side effects.
            if str(row[1]) == "audiobook.analyze" and str(row[0]) in {
                "leased", "running", "cancel_requested",
            }:
                work.jobs.cancel_active_job(context, job_id=job_id)
            else:
                work.jobs.request_cancel(context, job_id)
            work.commit()
        return {"job_id": job_id, "cancellation_requested": True}

    def pause_job(self, context: TenantContext, *, project_id: str,
                  job_id: str) -> dict[str, object]:
        """Pause one audiobook job, releasing queued work or requesting a safe stop."""
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            row = work.connection.execute(
                """SELECT status, job_type FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s AND module = 'audiobook'
                      AND input_payload->>'project_id' = %s FOR UPDATE""",
                (context.workspace_id, job_id, project_id),
            ).fetchone()
            if row is None or str(row[1]) not in {"audiobook.render-chapter", "audiobook.analyze"}:
                raise KeyError(job_id)
            status = str(row[0])
            if status in {"completed", "failed", "canceled", "stale", "cancel_requested"}:
                raise ValueError("only active audiobook jobs can be paused")
            if status == "paused":
                work.rollback()
                return {"job_id": job_id, "status": "paused", "paused": True}
            if status in {"queued", "waiting", "retrying"}:
                work.connection.execute(
                    """UPDATE omnix_jobs
                          SET status = 'paused',
                              metadata = (metadata - 'pause_requested') || %s::jsonb,
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    ('{"paused":true}', context.workspace_id, job_id),
                )
                result_status = "paused"
            else:
                work.connection.execute(
                    """UPDATE omnix_jobs
                          SET metadata = metadata || %s::jsonb,
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    ('{"pause_requested":true}', context.workspace_id, job_id),
                )
                result_status = "pause_requested"
            work.commit()
        return {"job_id": job_id, "status": result_status, "paused": True}

    def resume_job(self, context: TenantContext, *, project_id: str,
                   job_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            row = work.connection.execute(
                """SELECT status, job_type FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s AND module = 'audiobook'
                      AND input_payload->>'project_id' = %s FOR UPDATE""",
                (context.workspace_id, job_id, project_id),
            ).fetchone()
            if row is None or str(row[1]) not in {"audiobook.render-chapter", "audiobook.analyze"}:
                raise KeyError(job_id)
            status = str(row[0])
            if status == "paused":
                work.connection.execute(
                    """UPDATE omnix_jobs
                          SET status = 'queued', available_at = CURRENT_TIMESTAMP,
                              metadata = metadata - 'paused' - 'pause_requested',
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    (context.workspace_id, job_id),
                )
                result_status = "queued"
            elif status in {"leased", "running"}:
                work.connection.execute(
                    """UPDATE omnix_jobs
                          SET metadata = metadata - 'pause_requested',
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    (context.workspace_id, job_id),
                )
                result_status = status
            elif status == "cancel_requested":
                raise ValueError("a cancellation is already in progress")
            else:
                raise ValueError("only paused or active audiobook jobs can be resumed")
            work.commit()
        return {"job_id": job_id, "status": result_status, "resumed": True}

    def pause_render_queue(self, context: TenantContext, *, project_id: str,
                           resume: bool = False) -> dict[str, object]:
        """Pause or resume every render chapter in the current project queue."""
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            rows = work.connection.execute(
                """SELECT id, status FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type = 'audiobook.render-chapter'
                      AND input_payload->>'project_id' = %s
                      AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running', 'paused')
                    FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchall()
            changed = 0
            for job_id, raw_status in rows:
                status = str(raw_status)
                if resume:
                    if status == "paused":
                        work.connection.execute(
                            """UPDATE omnix_jobs
                                  SET status = 'queued', available_at = CURRENT_TIMESTAMP,
                                      metadata = metadata - 'paused' - 'pause_requested',
                                      updated_at = CURRENT_TIMESTAMP
                                WHERE workspace_id = %s AND id = %s""",
                            (context.workspace_id, str(job_id)),
                        )
                        changed += 1
                    elif status in {"leased", "running"}:
                        work.connection.execute(
                            """UPDATE omnix_jobs
                                  SET metadata = metadata - 'pause_requested',
                                      updated_at = CURRENT_TIMESTAMP
                                WHERE workspace_id = %s AND id = %s""",
                            (context.workspace_id, str(job_id)),
                        )
                        changed += 1
                elif status in {"queued", "waiting", "retrying"}:
                    work.connection.execute(
                        """UPDATE omnix_jobs
                              SET status = 'paused',
                                  metadata = (metadata - 'pause_requested') || %s::jsonb,
                                  updated_at = CURRENT_TIMESTAMP
                            WHERE workspace_id = %s AND id = %s""",
                        ('{"paused":true}', context.workspace_id, str(job_id)),
                    )
                    changed += 1
                elif status in {"leased", "running"}:
                    work.connection.execute(
                        """UPDATE omnix_jobs
                              SET metadata = metadata || %s::jsonb,
                                  updated_at = CURRENT_TIMESTAMP
                            WHERE workspace_id = %s AND id = %s""",
                        ('{"pause_requested":true}', context.workspace_id, str(job_id)),
                    )
                    changed += 1
            work.commit()
        return {"project_id": project_id, "resumed" if resume else "paused": changed}

    def stop_render_queue(self, context: TenantContext, *, project_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            rows = work.connection.execute(
                """SELECT id FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND job_type IN ('audiobook.render-chapter', 'audiobook.assemble-chapter')
                      AND input_payload->>'project_id' = %s
                      AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running', 'paused', 'cancel_requested')
                    FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchall()
            for (job_id,) in rows:
                work.jobs.request_cancel(context, str(job_id))
            work.commit()
        return {"project_id": project_id, "stopped": len(rows)}

    def retry_pipeline_job(
        self, context: TenantContext, *, project_id: str, job_id: str,
    ) -> dict[str, object]:
        allowed = {
            "audiobook.ingest": "cpu",
            "audiobook.analyze": "cpu",
            "audiobook.assemble-chapter": "cpu",
        }
        terminal = {"failed", "canceled", "stale"}
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id, lock=True)
            row = work.connection.execute(
                """SELECT job_type, status, resource_class, priority,
                          input_payload, max_attempts
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND id = %s
                      AND module = 'audiobook'
                      AND input_payload->>'project_id' = %s
                    FOR UPDATE""",
                (context.workspace_id, job_id, project_id),
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            job_type, status = str(row[0]), str(row[1])
            if job_type not in allowed:
                raise ValueError("this audiobook job type has its own retry flow")
            if status not in terminal:
                raise ValueError("only terminal audiobook jobs can be retried")
            payload = dict(row[4] or {})
            project = work.connection.execute(
                """SELECT current_source_revision_id,
                          settings->>'current_render_run_id'
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s FOR UPDATE""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            if job_type == "audiobook.ingest" and project[0] is not None:
                raise ValueError(
                    "ingest retry is stale because the project already has a canonical source; "
                    "upload the intended source again to create or recover a deliberate revision"
                )
            if job_type == "audiobook.analyze":
                if not project[0] or str(project[0]) != str(payload.get("source_revision_id")):
                    raise ValueError("analysis retry is stale for the current source revision")
            if job_type == "audiobook.assemble-chapter":
                if not project[1] or str(project[1]) != str(payload.get("render_run_id")):
                    raise ValueError("assembly retry is stale for the current render run")
            retry_id = f"ab:retry:{uuid4().hex}"
            work.jobs.create_job(context, {
                "id": retry_id,
                "module": "audiobook",
                "job_type": job_type,
                "resource_class": str(row[2]) or allowed[job_type],
                "priority": int(row[3]),
                "input_payload": payload,
                "max_attempts": max(3, int(row[5])),
                "metadata": {"retry_of": job_id},
            })
            work.connection.execute(
                """UPDATE omnix_jobs
                      SET metadata = metadata || %s::jsonb,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                ('{"superseded_by":"' + retry_id + '"}',
                 context.workspace_id, job_id),
            )
            if job_type == "audiobook.ingest":
                next_state = "imported" if project[0] is None else None
            else:
                next_state = {
                    "audiobook.analyze": "analyzing",
                    "audiobook.assemble-chapter": "mastering",
                }[job_type]
            if next_state is not None:
                work.connection.execute(
                    """UPDATE omnix_audiobook_projects
                          SET state = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    (next_state, context.workspace_id, project_id),
                )
            work.commit()
        return {"job_id": retry_id, "retry_of": job_id, "type": job_type}

    def reclassify_source(
        self, context: TenantContext, *, project_id: str,
    ) -> dict[str, str]:
        """Queue a fresh AI interpretation, migrating stale source spans first."""
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT p.current_source_revision_id,
                          p.settings->>'current_render_run_id',
                          r.original_asset_id,
                          r.source_format,
                          r.extractor_version,
                          r.extraction_settings
                     FROM omnix_audiobook_projects p
                     JOIN omnix_audiobook_source_revisions r
                       ON r.workspace_id = p.workspace_id
                      AND r.id = p.current_source_revision_id
                    WHERE p.workspace_id = %s AND p.id = %s
                      AND p.deleted_at IS NULL
                    FOR UPDATE OF p""",
                (context.workspace_id, project_id),
            ).fetchone()
            if project is None:
                raise KeyError(project_id)
            source_revision_id = project[0]
            if not source_revision_id:
                raise ValueError("project has no canonical source")

            active = work.connection.execute(
                """SELECT id
                     FROM omnix_jobs
                    WHERE workspace_id = %s AND module = 'audiobook'
                      AND input_payload->>'project_id' = %s
                      AND (
                          (
                              job_type = 'audiobook.analyze'
                              AND input_payload->>'source_revision_id' = %s
                          )
                          OR (
                              job_type = 'audiobook.ingest'
                              AND input_payload->>'force_reclassify' = 'true'
                          )
                      )
                      AND status IN ('queued', 'waiting', 'retrying', 'leased',
                                     'running', 'cancel_requested')
                    LIMIT 1
                    FOR UPDATE""",
                (context.workspace_id, project_id, str(source_revision_id)),
            ).fetchone()
            if active is not None:
                raise ValueError("classification is already running")

            stale_detector = bool(work.connection.execute(
                """SELECT EXISTS (
                       SELECT 1
                         FROM omnix_audiobook_spans s
                         JOIN omnix_audiobook_chapters c
                           ON c.workspace_id = s.workspace_id
                          AND c.id = s.chapter_id
                        WHERE c.workspace_id = %s
                          AND c.source_revision_id = %s
                          AND s.detector_version <> %s
                   )""",
                (context.workspace_id, str(source_revision_id), DETECTOR_VERSION),
            ).fetchone()[0])
            needs_reextract = (
                str(project[4]) != EXTRACTOR_VERSION or stale_detector
            )

            render_run_id = project[1]
            if render_run_id:
                render_jobs = work.connection.execute(
                    """SELECT id
                         FROM omnix_jobs
                        WHERE workspace_id = %s AND module = 'audiobook'
                          AND job_type IN ('audiobook.render-chapter',
                                           'audiobook.assemble-chapter')
                          AND input_payload->>'project_id' = %s
                          AND input_payload->>'render_run_id' = %s
                          AND status IN ('queued', 'waiting', 'retrying', 'leased',
                                         'running', 'paused', 'cancel_requested')
                        FOR UPDATE""",
                    (context.workspace_id, project_id, str(render_run_id)),
                ).fetchall()
                for (job_id,) in render_jobs:
                    work.jobs.request_cancel(context, str(job_id))

            if needs_reextract:
                job_id = f"ab:reextract:{uuid4().hex}"
                extraction_settings = dict(project[5] or {})
                work.jobs.create_job(context, {
                    "id": job_id,
                    "module": "audiobook",
                    "job_type": "audiobook.ingest",
                    "resource_class": "cpu",
                    "priority": 0,
                    "input_payload": {
                        "project_id": project_id,
                        "source_asset_id": str(project[2]),
                        "source_format": str(project[3]),
                        "extraction_settings": extraction_settings,
                        "force_reclassify": True,
                    },
                    "metadata": {
                        "reason": "user_requested_reclassification",
                        "migration": {
                            "from_source_revision_id": str(source_revision_id),
                            "from_extractor_version": str(project[4]),
                            "to_extractor_version": EXTRACTOR_VERSION,
                            "to_span_detector_version": DETECTOR_VERSION,
                        },
                    },
                    "max_attempts": 3,
                })
                next_state = "ingesting"
            else:
                job_id = f"ab:reclassify:{uuid4().hex}"
                work.jobs.create_job(context, {
                    "id": job_id,
                    "module": "audiobook",
                    "job_type": "audiobook.analyze",
                    "resource_class": "cpu",
                    "priority": 0,
                    "input_payload": {
                        "project_id": project_id,
                        "source_revision_id": str(source_revision_id),
                        "force_reclassify": True,
                    },
                    "metadata": {"reason": "user_requested_reclassification"},
                    "max_attempts": 3,
                })
                next_state = "analyzing"

            work.connection.execute(
                """UPDATE omnix_audiobook_projects
                      SET state = %s,
                          settings = settings - 'current_render_run_id',
                          settings_revision = settings_revision + 1,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s""",
                (next_state, context.workspace_id, project_id),
            )
            work.commit()

        return {
            "job_id": job_id,
            "source_revision_id": str(source_revision_id),
        }

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
        assert_model_revision(provider_id, model_id, model_revision)
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """
                SELECT current_source_revision_id, state FROM omnix_audiobook_projects
                 WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE
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
                       AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running', 'paused', 'cancel_requested')
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
        assert_model_revision(provider_id, model_id, model_revision)
        with unit_of_work(self.database) as work:
            project = work.connection.execute(
                """SELECT current_source_revision_id FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE""",
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
                                       chapter_id=chapter_id, span_id=span_id)
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
            self._require_active_project(work.connection, context, project_id)
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
            self._require_active_project(work.connection, context, project_id)
            rows = work.connection.execute(
                """SELECT e.id, e.format, e.manifest_hash, e.output_asset_id,
                          e.created_at, a.byte_size
                     FROM omnix_audiobook_exports e
                     JOIN omnix_assets a ON a.id = e.output_asset_id
                    WHERE e.workspace_id = %s AND e.project_id = %s
                      AND a.lifecycle_status = 'active'
                    ORDER BY e.created_at DESC""",
                (context.workspace_id, project_id),
            ).fetchall()
            work.rollback()
        return [{"id": row[0], "format": row[1], "manifest_hash": row[2],
                 "asset_id": row[3], "created_at": row[4].isoformat(),
                 "byte_size": row[5]} for row in rows]

    def open_export(self, context: TenantContext, *, project_id: str,
                    export_id: str) -> tuple[BinaryIO, str, str]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id)
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

        return (self.blobs.open_verified(str(row[1]), expected_checksum=str(row[2])),
                FORMAT_MIME[str(row[0])], str(row[0]))

    def read_export(self, context: TenantContext, *, project_id: str,
                    export_id: str) -> tuple[bytes, str, str]:
        """Bounded test/helper API; browser delivery uses open_export instead."""
        handle, mime, format = self.open_export(context, project_id=project_id,
                                                export_id=export_id)
        with handle:
            return handle.read(), mime, format

    def export_report(self, context: TenantContext, *, project_id: str,
                      export_id: str) -> dict[str, object]:
        with unit_of_work(self.database) as work:
            self._require_active_project(work.connection, context, project_id)
            work.rollback()
        return audit_export(self.database, self.blobs, context,
                            project_id=project_id, export_id=export_id)

    def submit_source(
        self, context: TenantContext, *, project_id: str,
        source_format: str, content: bytes, filename: str,
        extraction_settings: dict[str, object] | None = None,
    ) -> dict[str, str]:
        if source_format not in _MIME:
            raise UnsupportedSource(f"unsupported source format: {source_format}")
        if not content or len(content) > MAX_SOURCE_BYTES:
            raise UnsupportedSource("source is empty or exceeds the supported size limit")
        extraction_settings = normalize_extraction_settings(source_format, extraction_settings)
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
                    "metadata": {"filename": filename, "source_format": source_format,
                                 "extraction_settings": extraction_settings},
                })
                work.jobs.create_job(context, {
                    "id": job_id, "module": "audiobook", "job_type": "audiobook.ingest",
                    "resource_class": "cpu", "priority": 0,
                    "input_payload": {"project_id": project_id, "source_asset_id": asset_id,
                                      "source_format": source_format,
                                      "extraction_settings": extraction_settings},
                    "max_attempts": 3,
                })
                work.commit()
        except Exception:
            if blob["created"]:
                self.blobs.delete(storage_key)
            raise
        return {"project_id": project_id, "source_asset_id": asset_id, "job_id": job_id}
