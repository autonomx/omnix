"""Source-bound, reversible omissions from spoken text."""
from __future__ import annotations

from typing import Any


def load_speech_exclusions(connection: Any, context: Any, project_id: str, chapter_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """SELECT e.id, e.start_offset, e.end_offset, e.source_text
             FROM omnix_audiobook_speech_exclusions e
             JOIN omnix_audiobook_chapters c
               ON c.workspace_id = e.workspace_id AND c.canonical_hash = e.chapter_hash
              AND c.ordinal = e.chapter_ordinal
             JOIN omnix_audiobook_projects p
               ON p.workspace_id = c.workspace_id AND p.id = e.project_id
              AND p.current_source_revision_id = c.source_revision_id
            WHERE e.workspace_id = %s AND e.project_id = %s AND c.id = %s
              AND e.active AND p.deleted_at IS NULL
            ORDER BY e.start_offset, e.end_offset""",
        (context.workspace_id, project_id, chapter_id),
    ).fetchall()
    return [{"id": str(row[0]), "start_offset": int(row[1]), "end_offset": int(row[2]), "source_text": str(row[3])} for row in rows]


def exclusions_for_span(exclusions: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    return [{**item, "start_offset": max(start, item["start_offset"]) - start,
             "end_offset": min(end, item["end_offset"]) - start}
            for item in exclusions if item["start_offset"] < end and item["end_offset"] > start]
