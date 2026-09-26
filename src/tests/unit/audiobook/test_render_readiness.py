from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.audiobook.render_readiness import BookRenderReadiness, check_book_render_readiness
from app.audiobook.service import AudiobookService
from app.persistence.tenant import local_tenant_context


@pytest.mark.parametrize("condition,ready,message", [
    ("ready", True, None),
    ("active", False, "Wait for"),
    ("issues", False, 'Go to "Span review" and resolve 2'),
    ("unassigned", False, "Assign a speaker"),
    ("no_voice", False, "Assign a voice"),
    ("skipped", False, "skip all"),
    ("no_source", False, "Add a book"),
])
def test_readiness_checks_current_render_inputs(monkeypatch, condition, ready, message):
    class Connection:
        def execute(self, sql, params):
            if "FROM omnix_jobs" in sql:
                assert "source_revision_id" in sql and "paused" in sql
                return SimpleNamespace(fetchall=lambda: [("audiobook.analyze",)] if condition == "active" else [])
            assert "i.status = 'open'" in sql and "c.source_revision_id = %s" in sql
            return SimpleNamespace(fetchone=lambda: (2 if condition == "issues" else 0,))

    monkeypatch.setattr("app.audiobook.render_readiness.PostgresAudiobookRepository.list_chapters",
                        lambda *_args: [{"id": "chapter", "title": "Opening"}])

    def units(*_args, **_kwargs):
        if condition == "unassigned":
            raise ValueError("Assign a speaker")
        if condition == "no_voice":
            raise ValueError("Assign a voice")
        return [] if condition == "skipped" else [object()]

    monkeypatch.setattr("app.audiobook.render_readiness.load_chapter_units", units)
    result = check_book_render_readiness(
        Connection(), local_tenant_context(), project_id="book",
        source_revision_id=None if condition == "no_source" else "source",
    )
    assert result.public()["ready"] is ready
    if message:
        assert message in " ".join(result.blockers)
    else:
        assert result.chapters == [{"id": "chapter", "title": "Opening"}]


@pytest.mark.parametrize("job_type,message", [
    ("audiobook.ingest", 'go to "Span review"'),
    ("audiobook.analyze", 'use "Resume" or "Cancel"'),
    ("audiobook.render-chapter", 'Go to "Render & Export"'),
    ("audiobook.assemble-chapter", 'Go to "Render & Export"'),
])
def test_active_job_instructions_match_the_current_phase(job_type, message):
    connection = SimpleNamespace(execute=lambda *_args: SimpleNamespace(fetchall=lambda: [(job_type,)]))
    result = check_book_render_readiness(
        connection, local_tenant_context(), project_id="book", source_revision_id="source",
    )
    assert result.public()["ready"] is False
    assert message in result.blockers[0]


@pytest.mark.parametrize("blocked", [False, True])
def test_manual_book_can_render_without_classification_state(monkeypatch, blocked):
    queued = []
    connection = SimpleNamespace(execute=lambda *_args: SimpleNamespace(fetchone=lambda: ("source", "extracted")))
    work = SimpleNamespace(connection=connection, commit=lambda: None,
                           jobs=SimpleNamespace(create_job=lambda _context, payload: queued.append(payload)))

    @contextmanager
    def unit_of_work(_database):
        yield work

    monkeypatch.setattr("app.audiobook.service.unit_of_work", unit_of_work)
    monkeypatch.setattr("app.audiobook.service.assert_model_revision", lambda *_args: None)
    monkeypatch.setattr("app.audiobook.service.check_book_render_readiness", lambda *_args, **_kwargs: BookRenderReadiness(
        blockers=["Assign a voice"] if blocked else [],
        chapters=[{"id": "chapter", "title": "Opening"}], skipped_chapter_ids=["skipped"],
    ))
    service = AudiobookService(None, None)
    if blocked:
        with pytest.raises(ValueError, match="Assign a voice"):
            service.start_render(local_tenant_context(), project_id="book", model_revision="revision")
        assert not queued
    else:
        result = service.start_render(local_tenant_context(), project_id="book", model_revision="revision")
        assert result["source_chapter_count"] == 2
        assert len(queued) == 1
        assert queued[0]["input_payload"]["source_revision_id"] == "source"
