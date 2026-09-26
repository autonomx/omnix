from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.audiobook.service import AudiobookService
from app.audiobook.speech_exclusions import exclusions_for_span


def test_exclusions_follow_canonical_offsets_across_new_span_boundaries():
    items = [{"id": "exclude", "start_offset": 10, "end_offset": 17, "source_text": "Testing"}]
    assert exclusions_for_span(items, 8, 30)[0]["start_offset"] == 2
    assert exclusions_for_span(items, 0, 14)[0]["end_offset"] == 14
    assert exclusions_for_span(items, 14, 20)[0]["start_offset"] == 0
    assert exclusions_for_span(items, 17, 30) == []


@pytest.mark.parametrize("selected", ["Testing", "Changed"])
def test_service_validates_selected_occurrence_and_invalidates_current_audio(monkeypatch, selected):
    calls = []
    canceled = []
    class Connection:
        def execute(self, sql, params):
            calls.append((sql, params))
            if "SELECT s.source_text" in sql:
                assert params == ("workspace", "book", "span")
                return SimpleNamespace(fetchone=lambda: ("Testing again", 40, "chapter-hash", 2, "render-run"))
            if "INSERT INTO omnix_audiobook_speech_exclusions" in sql:
                return SimpleNamespace(fetchone=lambda: ("exclusion",))
            if "SELECT id FROM omnix_jobs" in sql:
                return SimpleNamespace(fetchall=lambda: [("job",)])
            assert "UPDATE omnix_audiobook_projects" in sql
            assert "current_render_run_id" in sql
            return None
    committed = []
    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=Connection(), commit=lambda: committed.append(True),
                              jobs=SimpleNamespace(request_cancel=lambda _context, job_id: canceled.append(job_id)))
    monkeypatch.setattr("app.audiobook.service.unit_of_work", work)
    service = AudiobookService(None, None)
    context = SimpleNamespace(workspace_id="workspace")
    if selected == "Changed":
        with pytest.raises(ValueError, match="no longer matches"):
            service.exclude_span_text(context, project_id="book", span_id="span", start_offset=0, end_offset=7, source_text=selected)
        assert len(calls) == 1
        assert not committed and not canceled
    else:
        assert service.exclude_span_text(context, project_id="book", span_id="span", start_offset=0, end_offset=7, source_text=selected) == {"id": "exclusion"}
        assert calls[1][1][1:] == ("workspace", "book", "chapter-hash", 2, 40, 47, "Testing")
        assert canceled == ["job"] and committed == [True]
