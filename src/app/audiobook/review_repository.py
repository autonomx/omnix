"""Explicit speaker, casting, and review decisions by immutable IDs."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.persistence.tenant import TenantContext

from .hashing import canonical_json


class PostgresAudiobookReviewRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def add_speaker(
        self, context: TenantContext, *, project_id: str, canonical_name: str,
    ) -> dict[str, str]:
        name = canonical_name.strip()
        if not name:
            raise ValueError("speaker name is required")
        project = self.connection.execute(
            "SELECT id FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, project_id),
        ).fetchone()
        if project is None:
            raise KeyError(project_id)
        speaker_id = str(uuid4())
        row = self.connection.execute(
            """
            INSERT INTO omnix_audiobook_speakers
                (id, workspace_id, project_id, canonical_name, display_name, kind)
            VALUES (%s::uuid, %s, %s, %s, %s, 'character')
            RETURNING id, canonical_name
            """, (speaker_id, context.workspace_id, project_id, name, name),
        ).fetchone()
        return {"id": str(row[0]), "canonical_name": str(row[1])}

    def list_speakers(self, context: TenantContext, project_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT s.id, s.canonical_name, s.display_name, s.kind,
                   c.id, c.voice_profile_id, c.voice_revision_hash, c.revision
              FROM omnix_audiobook_speakers AS s
              LEFT JOIN LATERAL (
                  SELECT id, voice_profile_id, voice_revision_hash, revision
                    FROM omnix_audiobook_castings
                   WHERE workspace_id = s.workspace_id AND speaker_id = s.id
                   ORDER BY revision DESC LIMIT 1
              ) AS c ON TRUE
             WHERE s.workspace_id = %s AND s.project_id = %s
             ORDER BY CASE WHEN s.kind = 'narrator' THEN 0 ELSE 1 END, s.canonical_name
            """, (context.workspace_id, project_id),
        ).fetchall()
        speakers = [{"id": str(row[0]), "canonical_name": str(row[1]),
                 "display_name": str(row[2]), "kind": str(row[3]),
                 "casting": ({"id": str(row[4]), "voice_profile_id": str(row[5]),
                              "voice_revision_hash": str(row[6]), "revision": int(row[7])}
                             if row[4] else None), "aliases": []} for row in rows]
        alias_rows = self.connection.execute(
            """SELECT speaker_id, alias FROM omnix_audiobook_speaker_aliases
                WHERE workspace_id = %s AND project_id = %s AND status = 'confirmed'
                ORDER BY alias""", (context.workspace_id, project_id),
        ).fetchall()
        by_id = {speaker["id"]: speaker for speaker in speakers}
        for speaker_id, alias in alias_rows:
            if str(speaker_id) in by_id:
                by_id[str(speaker_id)]["aliases"].append(str(alias))
        return speakers

    def confirm_alias(
        self, context: TenantContext, *, project_id: str,
        speaker_id: str, alias: str,
    ) -> dict[str, str]:
        UUID(speaker_id)
        name = alias.strip()
        if not name or len(name) > 128:
            raise ValueError("alias must be non-empty and at most 128 characters")
        speaker = self.connection.execute(
            """SELECT id FROM omnix_audiobook_speakers
                WHERE workspace_id = %s AND project_id = %s AND id = %s::uuid
                FOR UPDATE""", (context.workspace_id, project_id, speaker_id),
        ).fetchone()
        if speaker is None:
            raise KeyError(speaker_id)
        conflict = self.connection.execute(
            """SELECT id FROM omnix_audiobook_speakers
                WHERE workspace_id = %s AND project_id = %s
                  AND lower(canonical_name) = lower(%s) AND id <> %s::uuid""",
            (context.workspace_id, project_id, name, speaker_id),
        ).fetchone()
        if conflict:
            raise ValueError("alias matches another speaker's canonical name")
        existing = self.connection.execute(
            """SELECT id, speaker_id FROM omnix_audiobook_speaker_aliases
                WHERE workspace_id = %s AND project_id = %s
                  AND lower(alias) = lower(%s) AND status = 'confirmed'""",
            (context.workspace_id, project_id, name),
        ).fetchone()
        if existing:
            if str(existing[1]) != speaker_id:
                raise ValueError("alias is already assigned to another speaker")
            return {"id": str(existing[0]), "speaker_id": speaker_id, "alias": name}
        alias_id = f"ab:alias:{uuid4().hex}"
        self.connection.execute(
            """INSERT INTO omnix_audiobook_speaker_aliases
                (id, workspace_id, project_id, speaker_id, alias, provenance,
                 status, confirmed_by_user_id)
               VALUES (%s, %s, %s, %s::uuid, %s, %s::jsonb, 'confirmed', %s)""",
            (alias_id, context.workspace_id, project_id, speaker_id, name,
             canonical_json({"mode": "user_confirmed"}), context.user_id),
        )
        return {"id": alias_id, "speaker_id": speaker_id, "alias": name}

    def assign_voice(
        self, context: TenantContext, *, project_id: str, speaker_id: str,
        voice_profile_id: str, voice_revision_hash: str,
    ) -> dict[str, Any]:
        UUID(speaker_id)
        if len(voice_revision_hash) != 64:
            raise ValueError("voice revision hash is invalid")
        speaker = self.connection.execute(
            """
            SELECT id FROM omnix_audiobook_speakers
             WHERE workspace_id = %s AND project_id = %s AND id = %s::uuid FOR UPDATE
            """, (context.workspace_id, project_id, speaker_id),
        ).fetchone()
        if speaker is None:
            raise KeyError(speaker_id)
        current = self.connection.execute(
            """
            SELECT revision, voice_profile_id, voice_revision_hash
              FROM omnix_audiobook_castings
             WHERE workspace_id = %s AND speaker_id = %s::uuid
             ORDER BY revision DESC LIMIT 1
            """, (context.workspace_id, speaker_id),
        ).fetchone()
        if current and (str(current[1]), str(current[2])) == (voice_profile_id, voice_revision_hash):
            return {"speaker_id": speaker_id, "revision": int(current[0]),
                    "voice_profile_id": voice_profile_id, "voice_revision_hash": voice_revision_hash}
        revision = int(current[0]) + 1 if current else 1
        casting_id = f"ab:cast:{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO omnix_audiobook_castings
                (id, workspace_id, speaker_id, revision, voice_profile_id,
                 voice_revision_hash, provenance)
            VALUES (%s, %s, %s::uuid, %s, %s, %s, %s::jsonb)
            """, (casting_id, context.workspace_id, speaker_id, revision,
                  voice_profile_id, voice_revision_hash,
                  canonical_json({"confirmed_by_user_id": context.user_id})),
        )
        active_runs = self.connection.execute(
            """
            SELECT settings->>'current_render_run_id', state
              FROM omnix_audiobook_projects
             WHERE workspace_id = %s AND id = %s FOR UPDATE
            """, (context.workspace_id, project_id),
        ).fetchone()
        if active_runs and active_runs[1] in {"rendering", "mastering"} and active_runs[0]:
            rows = self.connection.execute(
                """
                SELECT id FROM omnix_jobs
                 WHERE workspace_id = %s AND module = 'audiobook'
                   AND job_type IN ('audiobook.render-chapter', 'audiobook.assemble-chapter')
                   AND input_payload->>'render_run_id' = %s
                   AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running')
                """, (context.workspace_id, str(active_runs[0])),
            ).fetchall()
            from app.persistence.job_repository import PostgresJobRepository

            jobs = PostgresJobRepository(self.connection)
            for row in rows:
                jobs.request_cancel(context, str(row[0]))
        self.connection.execute(
            """
            UPDATE omnix_audiobook_projects
               SET state = CASE WHEN state IN ('rendering', 'mastering', 'rendered', 'ready_to_export', 'exported')
                                THEN 'ready_to_render' ELSE state END,
                   settings = settings - 'current_render_run_id',
                   settings_revision = settings_revision + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s
            """, (context.workspace_id, project_id),
        )
        return {"id": casting_id, "speaker_id": speaker_id, "revision": revision,
                "voice_profile_id": voice_profile_id, "voice_revision_hash": voice_revision_hash}

    def resolve_issue(
        self, context: TenantContext, *, project_id: str, issue_id: str,
        speaker_id: str, role: str, delivery: str = "",
    ) -> dict[str, Any]:
        if role not in {"narration", "dialogue", "heading", "other"}:
            raise ValueError("invalid annotation role")
        UUID(speaker_id)
        row = self.connection.execute(
            """
            SELECT i.annotation_id, a.span_id, a.revision, s.structural_kind
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
             WHERE i.workspace_id = %s AND i.id = %s AND i.status = 'open'
               AND r.project_id = %s
             FOR UPDATE OF i
            """, (context.workspace_id, issue_id, project_id),
        ).fetchone()
        if row is None:
            raise KeyError(issue_id)
        speaker = self.connection.execute(
            "SELECT id FROM omnix_audiobook_speakers WHERE workspace_id = %s AND project_id = %s AND id = %s::uuid",
            (context.workspace_id, project_id, speaker_id),
        ).fetchone()
        if speaker is None:
            raise KeyError(speaker_id)
        if role == "dialogue" and row[3] != "dialogue":
            raise ValueError("narrative source cannot be assigned a dialogue voice")
        next_revision = int(self.connection.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM omnix_audiobook_annotations WHERE workspace_id = %s AND span_id = %s",
            (context.workspace_id, row[1]),
        ).fetchone()[0])
        annotation_id = f"ab:an:{uuid4().hex}"
        self.connection.execute(
            """
            INSERT INTO omnix_audiobook_annotations
                (id, workspace_id, span_id, revision, role, speaker_id, delivery,
                 evidence, classifier, review_status)
            VALUES (%s, %s, %s, %s, %s, %s::uuid, %s, %s::jsonb, %s::jsonb, 'user_resolved')
            """, (annotation_id, context.workspace_id, row[1], next_revision,
                  role, speaker_id, delivery,
                  canonical_json({"review_issue_id": issue_id}),
                  canonical_json({"mode": "user_decision", "user_id": context.user_id})),
        )
        self.connection.execute(
            """
            UPDATE omnix_audiobook_review_issues
               SET status = 'resolved', resolution = %s::jsonb, resolved_at = CURRENT_TIMESTAMP
             WHERE workspace_id = %s AND id = %s
            """, (canonical_json({"annotation_id": annotation_id,
                                    "speaker_id": speaker_id, "role": role,
                                    "user_id": context.user_id}),
                  context.workspace_id, issue_id),
        )
        remaining = int(self.connection.execute(
            """
            SELECT count(*) FROM omnix_audiobook_review_issues AS i
              JOIN omnix_audiobook_annotations AS a ON a.workspace_id = i.workspace_id AND a.id = i.annotation_id
              JOIN omnix_audiobook_spans AS s ON s.workspace_id = a.workspace_id AND s.id = a.span_id
              JOIN omnix_audiobook_chapters AS c ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
              JOIN omnix_audiobook_source_revisions AS r ON r.workspace_id = c.workspace_id AND r.id = c.source_revision_id
              JOIN omnix_audiobook_projects AS p ON p.workspace_id = r.workspace_id AND p.id = r.project_id AND p.current_source_revision_id = r.id
             WHERE i.workspace_id = %s AND i.status = 'open' AND r.project_id = %s
            """, (context.workspace_id, project_id),
        ).fetchone()[0])
        if remaining == 0:
            self.connection.execute(
                "UPDATE omnix_audiobook_projects SET state = 'ready_to_render', updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, project_id),
            )
        return {"annotation_id": annotation_id, "span_id": str(row[1]),
                "revision": next_revision, "remaining_review_issues": remaining}
