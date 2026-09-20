"""Initial deterministic interpretation and review queue persistence."""
from __future__ import annotations

from typing import Any

from app.persistence.tenant import TenantContext

from .annotation import SpanAnnotation, narrator_id
from .hashing import canonical_json, text_hash


class PostgresAudiobookAnalysisRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def prepare_review(
        self, context: TenantContext, *, project_id: str, source_revision_id: str,
        annotations: dict[str, SpanAnnotation] | None = None,
        classifier: dict[str, Any] | None = None,
        chapter_id: str | None = None,
        finalize: bool = True,
    ) -> dict[str, int]:
        project = self.connection.execute(
            """
            SELECT current_source_revision_id FROM omnix_audiobook_projects
             WHERE workspace_id = %s AND id = %s FOR UPDATE
            """, (context.workspace_id, project_id),
        ).fetchone()
        if project is None or str(project[0]) != source_revision_id:
            raise ValueError("analysis requires the current canonical source revision")
        narrator = narrator_id(project_id)
        self.connection.execute(
            """
            INSERT INTO omnix_audiobook_speakers
                (id, workspace_id, project_id, canonical_name, display_name, kind)
            VALUES (%s::uuid, %s, %s, 'Narrator', 'Narrator', 'narrator')
            ON CONFLICT (id) DO NOTHING
            """, (narrator, context.workspace_id, project_id),
        )
        spans = self.connection.execute(
            """
            SELECT s.id, s.structural_kind
              FROM omnix_audiobook_spans AS s
              JOIN omnix_audiobook_chapters AS c
                ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
             WHERE c.workspace_id = %s AND c.source_revision_id = %s
               AND (%s::text IS NULL OR c.id = %s)
             ORDER BY c.ordinal, s.ordinal
            """, (context.workspace_id, source_revision_id, chapter_id, chapter_id),
        ).fetchall()
        issues = 0
        for span_id, kind in spans:
            annotation_id = f"ab:an:{text_hash(f'{span_id}:1')}"
            interpreted = (annotations or {}).get(str(span_id))
            review_reason = interpreted.review_reason if interpreted else ("FALLBACK_NARRATOR" if kind == "dialogue" else None)
            review_required = review_reason is not None
            status = "review_required" if review_required else "confident"
            self.connection.execute(
                """
                INSERT INTO omnix_audiobook_annotations
                    (id, workspace_id, span_id, revision, role, speaker_id,
                     speaker_candidate, delivery, evidence, classifier, review_status)
                VALUES (%s, %s, %s, 1, %s, %s::uuid, %s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (span_id, revision) DO NOTHING
                """,
                (annotation_id, context.workspace_id, span_id,
                 interpreted.role if interpreted else kind,
                 interpreted.speaker_id if interpreted else narrator,
                 interpreted.speaker_candidate if interpreted else None,
                 interpreted.delivery if interpreted else "",
                 canonical_json({"detector_role": kind, "source_text_untouched": True,
                                 **(interpreted.evidence if interpreted else {})}),
                 canonical_json(classifier or {"mode": "deterministic_fallback", "version": "audiobook-analysis-v1"}),
                 status),
            )
            if review_required:
                issues += 1
                self.connection.execute(
                    """
                    INSERT INTO omnix_audiobook_review_issues
                        (id, workspace_id, annotation_id, reason, evidence)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (f"ab:ri:{text_hash(annotation_id)}", context.workspace_id,
                     annotation_id, review_reason,
                     canonical_json({"reason": review_reason,
                                     "speaker_candidate": interpreted.speaker_candidate if interpreted else None})),
                )
        if not finalize:
            return {"spans": len(spans), "review_issues": issues}
        return self.finalize_review(context, project_id=project_id,
                                    source_revision_id=source_revision_id)

    def finalize_review(
        self, context: TenantContext, *, project_id: str, source_revision_id: str,
    ) -> dict[str, int]:
        project = self.connection.execute(
            """SELECT current_source_revision_id FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()
        if project is None or str(project[0]) != source_revision_id:
            raise ValueError("analysis requires the current canonical source revision")
        coverage = self.connection.execute(
            """SELECT count(s.id), count(a.id)
                 FROM omnix_audiobook_spans s
                 JOIN omnix_audiobook_chapters c
                   ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
                 LEFT JOIN omnix_audiobook_annotations a
                   ON a.workspace_id = s.workspace_id AND a.span_id = s.id
                  AND a.revision = 1
                WHERE c.workspace_id = %s AND c.source_revision_id = %s""",
            (context.workspace_id, source_revision_id),
        ).fetchone()
        if int(coverage[0]) != int(coverage[1]):
            raise ValueError("analysis cannot finish before all spans are annotated")
        issue_total = self.connection.execute(
            """SELECT count(i.id)
                 FROM omnix_audiobook_review_issues i
                 JOIN omnix_audiobook_annotations a
                   ON a.workspace_id = i.workspace_id AND a.id = i.annotation_id
                 JOIN omnix_audiobook_spans s
                   ON s.workspace_id = a.workspace_id AND s.id = a.span_id
                 JOIN omnix_audiobook_chapters c
                   ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
                WHERE c.workspace_id = %s AND c.source_revision_id = %s
                  AND i.status = 'open'""",
            (context.workspace_id, source_revision_id),
        ).fetchone()[0]
        self.connection.execute(
            """
            UPDATE omnix_audiobook_projects
               SET state = %s, updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s
            """, ("review_required" if issue_total else "ready_to_render", context.workspace_id, project_id),
        )
        return {"spans": int(coverage[0]), "review_issues": int(issue_total)}

    def list_review_issues(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT i.id, i.reason, i.evidence, i.status, a.span_id, a.speaker_id,
                   s.source_text, c.id, c.title, c.ordinal, a.speaker_candidate,
                   s.structural_kind
              FROM omnix_audiobook_review_issues AS i
              JOIN omnix_audiobook_annotations AS a
                ON a.workspace_id = i.workspace_id AND a.id = i.annotation_id
              JOIN omnix_audiobook_spans AS s
                ON s.workspace_id = a.workspace_id AND s.id = a.span_id
              JOIN omnix_audiobook_chapters AS c
                ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
              JOIN omnix_audiobook_source_revisions AS r
                ON r.workspace_id = c.workspace_id AND r.id = c.source_revision_id
              JOIN omnix_audiobook_projects AS p
                ON p.workspace_id = r.workspace_id AND p.id = r.project_id
               AND p.current_source_revision_id = r.id
             WHERE i.workspace_id = %s AND r.project_id = %s AND i.status = 'open'
             ORDER BY c.ordinal, s.ordinal
            """, (context.workspace_id, project_id),
        ).fetchall()
        return [{"id": str(row[0]), "reason": str(row[1]), "evidence": dict(row[2]),
                 "status": str(row[3]), "span_id": str(row[4]), "speaker_id": str(row[5]) if row[5] else None,
                 "source_text": str(row[6]), "chapter_id": str(row[7]),
                 "chapter_title": str(row[8]), "chapter_ordinal": int(row[9]),
                 "speaker_candidate": str(row[10]) if row[10] else None,
                 "structural_kind": str(row[11])}
                for row in rows]
