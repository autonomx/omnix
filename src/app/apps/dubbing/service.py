"""Dubbing workflows and their transactions; no SQL."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .contracts import DubProject, DubSegment
from .repository import PostgresDubbingRepository
from .steps import STEPS, approved, take_is_current


class DubbingNotFound(LookupError):
    pass


class DubbingConflict(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _segment(row: dict[str, Any]) -> DubSegment:
    return DubSegment(**{key: row[key] for key in DubSegment.model_fields if key in row},
                      approved=approved(row), take_current=take_is_current(row),
                      budget_seconds=round(row["end_seconds"] - row["start_seconds"], 3))


def _project(row: dict[str, Any], segments: list[dict[str, Any]] | None = None) -> DubProject:
    lines = [_segment(segment) for segment in segments] if segments is not None else []
    return DubProject(**{key: row[key] for key in DubProject.model_fields if key in row},
                      segments=lines, line_count=len(lines), approved_count=sum(line.approved for line in lines))


def create_project(database: Any, context: TenantContext, *, title: str, source_asset_id: str,
                   source_language: str, target_language: str, translator: str = "", engine: str = "",
                   speakers: int = 0) -> DubProject:
    project_id = f"dub:{uuid.uuid4().hex}"
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        repository.create_project(context, {
            "id": project_id, "title": title, "source_asset_id": source_asset_id, "source_language": source_language,
            "target_language": target_language, "translator": translator, "engine": engine, "speakers": speakers,
        })
        row = repository.project(context, project_id)
        work.commit()
    assert row is not None
    return _project(row, [])


def list_projects(database: Any, context: TenantContext) -> list[DubProject]:
    with unit_of_work(database) as work:
        rows = PostgresDubbingRepository(work.connection).projects(context)
        work.rollback()
    return [_project(row) for row in rows]


def get_project(database: Any, context: TenantContext, project_id: str) -> DubProject:
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        row = repository.project(context, project_id)
        segments = repository.segments(context, project_id) if row else []
        work.rollback()
    if row is None:
        raise DubbingNotFound(project_id)
    return _project(row, segments)


def load_for_step(database: Any, context: TenantContext, project_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        row = repository.project(context, project_id)
        segments = repository.segments(context, project_id) if row else []
        work.rollback()
    if row is None:
        raise DubbingNotFound(project_id)
    return row, segments


def update_project(database: Any, context: TenantContext, project_id: str, **values: Any) -> DubProject:
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        if not repository.update_project(context, project_id, **values):
            raise DubbingNotFound(project_id)
        work.commit()
    return get_project(database, context, project_id)


def delete_project(database: Any, context: TenantContext, project_id: str) -> None:
    with unit_of_work(database) as work:
        if not PostgresDubbingRepository(work.connection).delete_project(context, project_id):
            raise DubbingNotFound(project_id)
        work.commit()


def mark_step(database: Any, context: TenantContext, project_id: str, step: str, status: str, *,
              job_id: str = "", error: str = "", detail: dict[str, Any] | None = None) -> None:
    """Record a step's state on the project (queued, running, done, failed)."""
    if step not in STEPS:
        raise ValueError(f"unknown dubbing step {step}")
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        row = repository.project(context, project_id, lock=True)
        if row is None:
            raise DubbingNotFound(project_id)
        steps = dict(row["steps"] or {})
        previous = dict(steps.get(step) or {})
        steps[step] = {"status": status, "job_id": job_id or previous.get("job_id", ""), "error": error,
                       "updated_at": _now(), **({"detail": detail} if detail else {})}
        repository.update_project(context, project_id, steps=steps)
        work.commit()


def apply_step_result(database: Any, context: TenantContext, project_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Store what a step produced: assets, duration, lines, translations, casting."""
    summary: dict[str, Any] = {}
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        row = repository.project(context, project_id, lock=True)
        if row is None:
            raise DubbingNotFound(project_id)
        values: dict[str, Any] = {}
        if result.get("assets"):
            values["assets"] = {**(row["assets"] or {}), **result["assets"]}
        if "duration_seconds" in result:
            values["duration_seconds"] = float(result["duration_seconds"])
        if "casting" in result:
            values["casting"] = result["casting"]
        if values:
            repository.update_project(context, project_id, **values)
        if "lines" in result:
            summary["lines"] = repository.replace_segments(context, project_id, result["lines"])
        revisions = result.get("translation_revisions") or {}
        for segment_id, text in (result.get("translations") or {}).items():
            # Only lines still as the step read them; a line asked for again may replace a person's words.
            repository.set_translation(context, project_id, segment_id, text, "llm",
                                       expected_revision=revisions.get(segment_id),
                                       replace_person=bool(result.get("requested_lines")))
        summary.update({key: result[key] for key in ("fit", "uncast") if key in result})
        work.commit()
    return summary


def save_translation(database: Any, context: TenantContext, project_id: str, segment_id: str, text: str,
                     origin: str, *, expected_revision: int | None = None) -> int | None:
    """Store new words for a line; returns its translation revision.

    With ``expected_revision`` (a machine rewrite) it returns None when the line moved on meanwhile or a
    person wrote its words (theirs are kept), and ``expected_revision`` itself when the words are unchanged.
    """
    text = " ".join(text.split())
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        changed = repository.set_translation(context, project_id, segment_id, text, origin,
                                             expected_revision=expected_revision)
        segment = next((row for row in repository.segments(context, project_id) if row["id"] == segment_id), None)
        work.commit()
    if segment is None:
        raise DubbingNotFound(segment_id)
    if expected_revision is not None and not changed:
        unchanged = (segment.get("translation") == text and int(segment["translation_revision"]) == expected_revision
                     and segment.get("translation_origin") != "person")
        return expected_revision if unchanged else None
    return int(segment["translation_revision"])


def save_take(database: Any, context: TenantContext, project_id: str, segment_id: str, **take: Any) -> None:
    with unit_of_work(database) as work:
        if not PostgresDubbingRepository(work.connection).set_take(context, project_id, segment_id, **take):
            raise DubbingNotFound(segment_id)
        work.commit()


def edit_line(database: Any, context: TenantContext, project_id: str, segment_id: str, *,
              translation: str | None = None, voice_override: str | None = None) -> DubProject:
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        if repository.project(context, project_id) is None:
            raise DubbingNotFound(project_id)
        if translation is not None:
            repository.set_translation(context, project_id, segment_id, " ".join(translation.split()), "person")
        if voice_override is not None and not repository.set_voice_override(context, project_id, segment_id,
                                                                              voice_override.strip()):
            raise DubbingNotFound(segment_id)
        work.commit()
    return get_project(database, context, project_id)


def set_approval(database: Any, context: TenantContext, project_id: str, segment_ids: list[str],
                 approve: bool) -> DubProject:
    """Approve (or withdraw approval of) lines; a line without a current take cannot be approved."""
    with unit_of_work(database) as work:
        repository = PostgresDubbingRepository(work.connection)
        if repository.project(context, project_id) is None:
            raise DubbingNotFound(project_id)
        if approve:
            changed = repository.approve(context, project_id, segment_ids)
            if changed < len(set(segment_ids)):
                work.rollback()
                raise DubbingConflict("a line needs a take of its current translation before it can be approved")
        else:
            repository.unapprove(context, project_id, segment_ids)
        work.commit()
    return get_project(database, context, project_id)
