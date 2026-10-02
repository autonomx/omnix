"""PostgreSQL access for audiobook project state and project-scoped reads.

``AudiobookService`` owns the workflow decisions; this repository owns every
statement it runs against the audiobook tables. Methods return database rows
unchanged so the service keeps one place for turning rows into API payloads.
"""
from __future__ import annotations

from typing import Any, Sequence

from app.persistence.tenant import TenantContext

from .hashing import canonical_json

class PostgresAudiobookProjectRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    # -- project row: locks and reads -------------------------------------

    def require_active(self, context: TenantContext, project_id: str, *,
                       lock: bool = False) -> None:
        locking = " FOR UPDATE" if lock else ""
        row = self.connection.execute(
            "SELECT 1 FROM omnix_audiobook_projects "
            "WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL" + locking,
            (context.workspace_id, project_id),
        ).fetchone()
        if row is None:
            raise KeyError(project_id)

    def lock_active(self, context: TenantContext, project_id: str) -> Any:
        """``(id,)`` of a live project, locked; ``None`` if it is missing or deleted."""
        return self.connection.execute(
            """SELECT id FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_classification_rules(self, context: TenantContext, project_id: str) -> Any:
        """``(classification_rules,)``, locked against concurrent submissions."""
        return self.connection.execute(
            """SELECT settings->>'classification_rules'
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_render_settings(self, context: TenantContext, project_id: str) -> Any:
        """``(state, current_render_run_id)``, locked."""
        return self.connection.execute(
            """SELECT state, settings->>'current_render_run_id'
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_render_run(self, context: TenantContext, project_id: str) -> Any:
        """``(current_render_run_id,)``, locked."""
        return self.connection.execute(
            """SELECT settings->>'current_render_run_id' FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_for_override(self, context: TenantContext, project_id: str) -> Any:
        """``(current_source_revision_id, state, current_render_run_id)``, locked."""
        return self.connection.execute(
            """SELECT current_source_revision_id, state,
                      settings->>'current_render_run_id'
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_revision_and_run(self, context: TenantContext, project_id: str) -> Any:
        """``(current_source_revision_id, current_render_run_id)``, locked.

        Callers have already locked the project as active in this transaction.
        """
        return self.connection.execute(
            """SELECT current_source_revision_id,
                      settings->>'current_render_run_id'
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_render_source(self, context: TenantContext, project_id: str) -> Any:
        """``(current_source_revision_id, state)``, locked."""
        return self.connection.execute(
            """
            SELECT current_source_revision_id, state FROM omnix_audiobook_projects
             WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE
            """, (context.workspace_id, project_id),
        ).fetchone()

    def lock_current_revision(self, context: TenantContext, project_id: str) -> Any:
        """``(current_source_revision_id,)``, locked."""
        return self.connection.execute(
            """SELECT current_source_revision_id FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_cover(self, context: TenantContext, project_id: str) -> Any:
        """``(cover_asset_id,)``, locked."""
        return self.connection.execute(
            """SELECT cover_asset_id
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()

    def lock_with_current_revision(self, context: TenantContext, project_id: str) -> Any:
        """The project and its current source revision, with the project locked.

        ``(current_source_revision_id, current_render_run_id, original_asset_id,
        source_format, extractor_version, extraction_settings,
        classification_rules, quote_extraction_rules)``.
        """
        return self.connection.execute(
            """SELECT p.current_source_revision_id,
                      p.settings->>'current_render_run_id',
                      r.original_asset_id,
                      r.source_format,
                      r.extractor_version,
                      r.extraction_settings,
                      p.settings->>'classification_rules',
                      p.settings->>'quote_extraction_rules'
                 FROM omnix_audiobook_projects p
                 JOIN omnix_audiobook_source_revisions r
                   ON r.workspace_id = p.workspace_id
                  AND r.id = p.current_source_revision_id
                WHERE p.workspace_id = %s AND p.id = %s
                  AND p.deleted_at IS NULL
                FOR UPDATE OF p""",
            (context.workspace_id, project_id),
        ).fetchone()

    def structure_settings(self, context: TenantContext, project_id: str) -> Any:
        """``(current_source_revision_id, settings)``."""
        return self.connection.execute(
            """SELECT current_source_revision_id, settings
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL""",
            (context.workspace_id, project_id),
        ).fetchone()

    # -- project row: writes ----------------------------------------------

    def save_classification_rules(self, context: TenantContext, project_id: str,
                                  rules: str) -> bool:
        row = self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET settings = jsonb_set(settings, '{classification_rules}', to_jsonb(%s::text), true),
                      settings_revision = settings_revision + 1,
                      updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL
                RETURNING id""",
            (rules, context.workspace_id, project_id),
        ).fetchone()
        return row is not None

    def update_metadata(self, context: TenantContext, project_id: str, *,
                        title: str, author: str) -> Any:
        """``(id, title, author, language, state, current_source_revision_id)`` or ``None``."""
        return self.connection.execute(
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

    def mark_deleted(self, context: TenantContext, project_id: str) -> None:
        self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET deleted_at = CURRENT_TIMESTAMP,
                      current_source_revision_id = NULL,
                      state = 'deleted',
                      settings = settings - 'current_render_run_id',
                      updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL""",
            (context.workspace_id, project_id),
        )

    def reset_render(self, context: TenantContext, project_id: str) -> None:
        """Drop the current render run; rendered projects return to ``ready_to_render``."""
        self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET state = CASE WHEN state IN ('rendering', 'mastering', 'rendered', 'ready_to_export', 'exported')
                                   THEN 'ready_to_render' ELSE state END,
                      settings = settings - 'current_render_run_id',
                      settings_revision = settings_revision + 1, updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s""",
            (context.workspace_id, project_id),
        )

    def set_audiobook_mode(self, context: TenantContext, project_id: str, mode: str) -> None:
        """Store the reading mode and drop the render run it invalidates."""
        self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET settings = jsonb_set(
                          settings - 'current_render_run_id',
                          '{audiobook_mode}', to_jsonb(%s::text), true
                      ),
                      state = CASE
                          WHEN state IN ('rendering', 'mastering', 'rendered', 'ready_to_export', 'exported')
                          THEN 'ready_to_render' ELSE state END,
                      settings_revision = settings_revision + 1,
                      updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s""",
            (mode, context.workspace_id, project_id),
        )

    def set_state_clearing_render(self, context: TenantContext, project_id: str,
                                  state: str) -> None:
        self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET state = %s,
                      settings = settings - 'current_render_run_id',
                      settings_revision = settings_revision + 1,
                      updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s""",
            (state, context.workspace_id, project_id),
        )

    def set_state(self, context: TenantContext, project_id: str, state: str) -> None:
        self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET state = %s, updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s""",
            (state, context.workspace_id, project_id),
        )

    def start_render_run(self, context: TenantContext, project_id: str,
                         render_run_id: str) -> None:
        self.connection.execute(
            """
            UPDATE omnix_audiobook_projects
               SET state = 'rendering',
                   settings = jsonb_set(settings, '{current_render_run_id}', to_jsonb(%s::text), true),
                   settings_revision = settings_revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s
            """, (render_run_id, context.workspace_id, project_id),
        )

    def set_cover(self, context: TenantContext, project_id: str,
                  asset_id: str | None) -> None:
        """Set or clear the cover; an exported book needs exporting again."""
        self.connection.execute(
            """UPDATE omnix_audiobook_projects
                  SET cover_asset_id = %s,
                      state = CASE WHEN state = 'exported' THEN 'ready_to_export' ELSE state END,
                      settings_revision = settings_revision + 1,
                      updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s""",
            (asset_id, context.workspace_id, project_id),
        )

    # -- project page projections -------------------------------------------

    def cover_summary(self, context: TenantContext, project_id: str) -> Any:
        """``(cover_asset_id, settings, cover_created_at)``."""
        return self.connection.execute(
            """SELECT p.cover_asset_id, p.settings, a.created_at
                 FROM omnix_audiobook_projects p
                 LEFT JOIN omnix_assets a
                   ON a.workspace_id = p.workspace_id AND a.id = p.cover_asset_id
                  AND a.lifecycle_status = 'active'
                WHERE p.workspace_id = %s AND p.id = %s""",
            (context.workspace_id, project_id),
        ).fetchone()

    def source_summary(self, context: TenantContext, project_id: str) -> Any:
        """``(source_format, filename, byte_size, created_at)`` of the current source."""
        return self.connection.execute(
            """SELECT r.source_format, a.metadata->>'filename', a.byte_size, a.created_at
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

    def chapter_summaries(self, context: TenantContext, source_revision_id: str) -> list[Any]:
        """``(id, ordinal, title, canonical_hash, character_count, span_count)`` per chapter."""
        return self.connection.execute(
            """SELECT id, ordinal, title, canonical_hash,
                      length(canonical_text),
                      (SELECT count(*) FROM omnix_audiobook_spans s
                        WHERE s.workspace_id = c.workspace_id
                          AND s.chapter_id = c.id)
                 FROM omnix_audiobook_chapters AS c
                WHERE c.workspace_id = %s AND c.source_revision_id = %s
                ORDER BY ordinal""",
            (context.workspace_id, source_revision_id),
        ).fetchall()

    def chapter_texts(self, context: TenantContext, source_revision_id: str) -> list[Any]:
        """``(canonical_text,)`` per chapter, in chapter order."""
        return self.connection.execute(
            """SELECT canonical_text
                 FROM omnix_audiobook_chapters
                WHERE workspace_id = %s AND source_revision_id = %s
                ORDER BY ordinal""",
            (context.workspace_id, source_revision_id),
        ).fetchall()

    def assembled_runtime_seconds(self, context: TenantContext,
                                  source_revision_id: str) -> float:
        """Sum of each chapter's latest assembled duration."""
        row = self.connection.execute(
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
            (context.workspace_id, source_revision_id),
        ).fetchone()
        return float(row[0] or 0.0)

    def render_key_counts(self, context: TenantContext,
                          job_ids: Sequence[str]) -> tuple[int, int]:
        """``(desired, completed)`` render keys across the given render jobs."""
        row = self.connection.execute(
            """
            SELECT COALESCE(sum(jsonb_array_length(b.desired_keys)), 0),
                   COALESCE(sum(jsonb_array_length(b.completed_keys)), 0)
              FROM omnix_audiobook_render_batches AS b
             WHERE b.workspace_id = %s AND b.job_id = ANY(%s)
            """, (context.workspace_id, list(job_ids)),
        ).fetchone()
        return int(row[0]), int(row[1])

    def recent_export_manifests(self, context: TenantContext, project_id: str) -> list[Any]:
        """``(job_id, format, manifest_id, manifest_hash)``, newest 20."""
        return self.connection.execute(
            """SELECT job_id, format, id, manifest_hash
                 FROM omnix_audiobook_export_manifests
                WHERE workspace_id = %s AND project_id = %s
                ORDER BY created_at DESC LIMIT 20""",
            (context.workspace_id, project_id),
        ).fetchall()

    # -- chapters, spans and annotations ----------------------------------

    def current_chapter(self, context: TenantContext, project_id: str,
                        chapter_id: str) -> Any:
        """A chapter of the project's current source revision.

        ``(id, ordinal, title, canonical_text, canonical_hash,
        source_revision_id, project_state, project_settings)``.
        """
        return self.connection.execute(
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

    def chapter_in_revision(self, context: TenantContext, chapter_id: str,
                            source_revision_id: Any) -> bool:
        return self.connection.execute(
            """SELECT id FROM omnix_audiobook_chapters
                WHERE workspace_id = %s AND id = %s AND source_revision_id = %s""",
            (context.workspace_id, chapter_id, source_revision_id),
        ).fetchone() is not None

    def latest_annotations(self, context: TenantContext, chapter_id: str, *,
                           include_unresolved: bool) -> list[Any]:
        """Each span's latest annotation, in span order.

        ``(span_id, annotation_id, revision, role, speaker_id, speaker_candidate,
        delivery, evidence, review_status)``; the annotation columns are
        ``None`` for unannotated spans. Without ``include_unresolved`` only
        user-resolved annotations are returned.
        """
        return self.connection.execute(
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
                  AND (%s::boolean OR a.review_status = 'user_resolved')
                ORDER BY s.ordinal""",
            (context.workspace_id, chapter_id, include_unresolved),
        ).fetchall()

    def lock_current_span(self, context: TenantContext, project_id: str,
                          span_id: str) -> Any:
        """A span of the current source, with the project locked.

        ``(source_text, start_offset, chapter_hash, chapter_ordinal,
        current_render_run_id)``.
        """
        return self.connection.execute(
            """SELECT s.source_text, s.start_offset, c.canonical_hash, c.ordinal,
                      p.settings->>'current_render_run_id'
                 FROM omnix_audiobook_projects p
                 JOIN omnix_audiobook_chapters c ON c.workspace_id = p.workspace_id
                  AND c.source_revision_id = p.current_source_revision_id
                 JOIN omnix_audiobook_spans s ON s.workspace_id = c.workspace_id AND s.chapter_id = c.id
                WHERE p.workspace_id = %s AND p.id = %s AND s.id = %s AND p.deleted_at IS NULL
                FOR UPDATE OF p""",
            (context.workspace_id, project_id, span_id),
        ).fetchone()

    def has_stale_spans(self, context: TenantContext, source_revision_id: str,
                        detector_version: str) -> bool:
        return bool(self.connection.execute(
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
            (context.workspace_id, source_revision_id, detector_version),
        ).fetchone()[0])

    def has_open_missed_dialogue(self, context: TenantContext,
                                 source_revision_id: str) -> bool:
        return bool(self.connection.execute(
            """SELECT EXISTS (
                   SELECT 1
                     FROM omnix_audiobook_review_issues i
                     JOIN omnix_audiobook_annotations a
                       ON a.workspace_id = i.workspace_id
                      AND a.id = i.annotation_id
                     JOIN omnix_audiobook_spans s
                       ON s.workspace_id = a.workspace_id
                      AND s.id = a.span_id
                     JOIN omnix_audiobook_chapters c
                       ON c.workspace_id = s.workspace_id
                      AND c.id = s.chapter_id
                    WHERE i.workspace_id = %s
                      AND c.source_revision_id = %s
                      AND i.status = 'open'
                      AND i.reason = 'POSSIBLE_MISSED_DIALOGUE'
               )""",
            (context.workspace_id, source_revision_id),
        ).fetchone()[0])

    # -- speech exclusions and pronunciations -----------------------------

    def upsert_speech_exclusion(
        self, context: TenantContext, project_id: str, *, exclusion_id: str,
        chapter_hash: Any, chapter_ordinal: Any, start_offset: int,
        end_offset: int, source_text: str,
    ) -> str:
        """Record (or reactivate) an exclusion; returns its id."""
        row = self.connection.execute(
            """INSERT INTO omnix_audiobook_speech_exclusions
                   (id, workspace_id, project_id, chapter_hash, chapter_ordinal, start_offset, end_offset, source_text)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                 ON CONFLICT (workspace_id, project_id, chapter_hash, chapter_ordinal, start_offset, end_offset)
                 DO UPDATE SET active = TRUE, updated_at = CURRENT_TIMESTAMP
                 RETURNING id""",
            (exclusion_id, context.workspace_id, project_id, chapter_hash, chapter_ordinal,
             start_offset, end_offset, source_text),
        ).fetchone()
        return str(row[0])

    def deactivate_speech_exclusion(self, context: TenantContext, project_id: str,
                                    exclusion_id: str) -> bool:
        row = self.connection.execute(
            """UPDATE omnix_audiobook_speech_exclusions SET active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND project_id = %s AND id = %s RETURNING id""",
            (context.workspace_id, project_id, exclusion_id),
        ).fetchone()
        return row is not None

    def current_pronunciations(self, context: TenantContext, project_id: str) -> list[Any]:
        """``(source_term, spoken_term, revision)``: the latest revision of each term."""
        return self.connection.execute(
            """SELECT DISTINCT ON (source_term) source_term, spoken_term, revision
                 FROM omnix_audiobook_pronunciations
                WHERE workspace_id = %s AND project_id = %s
                ORDER BY source_term, revision DESC""",
            (context.workspace_id, project_id),
        ).fetchall()

    def latest_pronunciation(self, context: TenantContext, project_id: str,
                             source_term: str) -> Any:
        """``(revision, spoken_term)`` of the term's latest revision, or ``None``."""
        return self.connection.execute(
            """SELECT revision, spoken_term FROM omnix_audiobook_pronunciations
                WHERE workspace_id = %s AND project_id = %s AND source_term = %s
                ORDER BY revision DESC LIMIT 1""",
            (context.workspace_id, project_id, source_term),
        ).fetchone()

    def append_pronunciation(
        self, context: TenantContext, project_id: str, *, pronunciation_id: str,
        revision: int, source_term: str, spoken_term: str,
    ) -> None:
        self.connection.execute(
            """INSERT INTO omnix_audiobook_pronunciations
                (id, workspace_id, project_id, revision, source_term,
                 spoken_term, settings)
               VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
            (pronunciation_id, context.workspace_id, project_id,
             revision, source_term, spoken_term,
             canonical_json({"confirmed_by_user_id": context.user_id})),
        )

    # -- assets: cover, source, exports, renders --------------------------

    def cover_blob(self, context: TenantContext, project_id: str) -> Any:
        """``(storage_key, checksum_sha256, mime_type)`` of the active cover."""
        return self.connection.execute(
            """SELECT a.storage_key, a.checksum_sha256, a.mime_type
                 FROM omnix_audiobook_projects p
                 JOIN omnix_assets a ON a.workspace_id = p.workspace_id
                                    AND a.id = p.cover_asset_id
                WHERE p.workspace_id = %s AND p.id = %s AND p.deleted_at IS NULL
                  AND a.lifecycle_status = 'active'""",
            (context.workspace_id, project_id),
        ).fetchone()

    def current_source_blob(self, context: TenantContext, project_id: str) -> Any:
        """``(storage_key, checksum_sha256, mime_type, source_format, filename)``."""
        return self.connection.execute(
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

    def lock_asset(self, context: TenantContext, asset_id: str) -> Any:
        """``(id, storage_key, revision, lifecycle_status)``, locked."""
        return self.connection.execute(
            """SELECT id, storage_key, revision, lifecycle_status
                 FROM omnix_assets
                WHERE workspace_id = %s AND id = %s
                FOR UPDATE""",
            (context.workspace_id, asset_id),
        ).fetchone()

    def is_export_output(self, context: TenantContext, project_id: str,
                         asset_id: str) -> bool:
        return self.connection.execute(
            """SELECT id
                 FROM omnix_audiobook_exports
                WHERE workspace_id = %s AND project_id = %s
                  AND output_asset_id = %s""",
            (context.workspace_id, project_id, asset_id),
        ).fetchone() is not None

    def is_source_original(self, context: TenantContext, project_id: str,
                           asset_id: str) -> bool:
        return self.connection.execute(
            """SELECT 1
                 FROM omnix_audiobook_source_revisions
                WHERE workspace_id = %s AND project_id = %s
                  AND original_asset_id = %s
                LIMIT 1""",
            (context.workspace_id, project_id, asset_id),
        ).fetchone() is not None

    def render_audio(self, context: TenantContext, render_id: str) -> Any:
        """``(audio_asset_id, audio_checksum)`` of a render, or ``None``."""
        return self.connection.execute(
            """SELECT audio_asset_id, audio_checksum FROM omnix_audiobook_renders
                WHERE workspace_id = %s AND id = %s""",
            (context.workspace_id, render_id),
        ).fetchone()

    def list_exports(self, context: TenantContext, project_id: str) -> list[Any]:
        """``(id, format, manifest_hash, output_asset_id, created_at, byte_size,
        asset_created_at)`` for active exports, newest first."""
        return self.connection.execute(
            """SELECT e.id, e.format, e.manifest_hash, e.output_asset_id,
                      e.created_at, a.byte_size, a.created_at
                 FROM omnix_audiobook_exports e
                 JOIN omnix_assets a ON a.id = e.output_asset_id AND a.workspace_id = e.workspace_id
                WHERE e.workspace_id = %s AND e.project_id = %s
                  AND a.lifecycle_status = 'active'
                ORDER BY e.created_at DESC""",
            (context.workspace_id, project_id),
        ).fetchall()

    def export_blob(self, context: TenantContext, project_id: str, export_id: str) -> Any:
        """``(format, storage_key, checksum_sha256)`` of an active export."""
        return self.connection.execute(
            """SELECT e.format, a.storage_key, a.checksum_sha256
                 FROM omnix_audiobook_exports e
                 JOIN omnix_assets a ON a.id = e.output_asset_id
                WHERE e.workspace_id = %s AND e.project_id = %s AND e.id = %s
                  AND a.lifecycle_status = 'active'""",
            (context.workspace_id, project_id, export_id),
        ).fetchone()
