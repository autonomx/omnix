"""Check current render inputs independently of how speakers were assigned."""
from dataclasses import dataclass, field
from typing import Any

from .render_planner import load_chapter_units
from .repository import PostgresAudiobookRepository


@dataclass
class BookRenderReadiness:
    blockers: list[str] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    skipped_chapter_ids: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {"ready": not self.blockers, "blockers": self.blockers}


def check_book_render_readiness(connection, context, *, project_id, source_revision_id):
    result = BookRenderReadiness()
    if not source_revision_id:
        result.blockers.append('Add a book: open "Book source", upload a file or choose one from the local library, then wait for quote extraction and review the spans.')
        return result
    active = connection.execute(
        """SELECT job_type FROM omnix_jobs
            WHERE workspace_id = %s AND module = 'audiobook'
              AND input_payload->>'project_id' = %s
              AND job_type IN ('audiobook.ingest', 'audiobook.analyze',
                               'audiobook.render-chapter', 'audiobook.assemble-chapter')
              AND status IN ('queued', 'waiting', 'retrying', 'leased', 'running',
                             'paused', 'cancel_requested')
              AND (job_type = 'audiobook.ingest'
                   OR input_payload->>'source_revision_id' = %s)""",
        (context.workspace_id, project_id, str(source_revision_id)),
    ).fetchall()
    if active:
        job_types = {row[0] for row in active}
        if "audiobook.ingest" in job_types:
            result.blockers.append('Wait for quote extraction to finish, then go to "Span review" to review the quotes before clicking "Classify text".')
        elif "audiobook.analyze" in job_types:
            result.blockers.append('Wait for text classification to finish, then go to "Span review" and resolve any review issues. If classification is paused, use "Resume" or "Cancel" in its progress controls.')
        else:
            result.blockers.append('Rendering or chapter assembly is already in progress. Go to "Render & Export" to check progress, resume paused chapter jobs, or stop the current render before starting another.')
        return result
    issues = connection.execute(
        """SELECT count(*) FROM omnix_audiobook_review_issues i
            JOIN omnix_audiobook_annotations a ON a.workspace_id = i.workspace_id AND a.id = i.annotation_id
            JOIN omnix_audiobook_spans s ON s.workspace_id = a.workspace_id AND s.id = a.span_id
            JOIN omnix_audiobook_chapters c ON c.workspace_id = s.workspace_id AND c.id = s.chapter_id
            WHERE c.workspace_id = %s AND c.source_revision_id = %s AND i.status = 'open'""",
        (context.workspace_id, str(source_revision_id)),
    ).fetchone()[0]
    if issues:
        result.blockers.append(f'Go to "Span review" and resolve {issues} open review issue(s): confirm the speaker and role for each flagged passage and click "Save interpretation" before rendering.')
    chapters = PostgresAudiobookRepository(connection).list_chapters(context, str(source_revision_id))
    if not chapters:
        result.blockers.append('No chapters are available. Open "Book source" and add or replace the source book, then wait for quote extraction and review the spans.')
    for chapter in chapters:
        try:
            units = load_chapter_units(connection, context, project_id=project_id, chapter_id=chapter["id"])
        except ValueError as exc:
            result.blockers.append(f"{chapter['title']}: {exc}")
            continue
        if units:
            result.chapters.append(chapter)
        else:
            result.skipped_chapter_ids.append(str(chapter["id"]))
    if chapters and not result.chapters and not result.blockers:
        result.blockers.append('The reading mode or text removals skip all source content. Review the reading mode in "Book source" and removed text in "Span review", then restore the content you want to read.')
    return result
