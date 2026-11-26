from __future__ import annotations

import pytest

from app.apps.audiobook.step_approvals import approval_basis, approval_blocker, approval_status


def _project(**overrides):
    project = {
        "current_source_revision_id": "source", "state": "ready_to_render", "review_issues": [],
        "pipeline_jobs": [],
        "speakers": [{"id": "narrator", "casting": {"id": "casting-one", "revision": 1}}],
        "render_jobs": [{"id": "render-one", "status": "completed"}],
    }
    project.update(overrides)
    return project


def _approved(step, project, **inputs):
    return {"step_approvals": {step: approval_basis(step, project, **inputs)}}


INPUTS = {"analysis_job_id": "analyze-one", "render_run_id": "run-one"}


@pytest.mark.parametrize("step,overrides,blocker", [
    ("speakers", {}, None),
    ("speakers", {"review_issues": [{"id": "issue"}]}, "Confirm the speaker for 1 line first."),
    ("speakers", {"state": "extracted"}, "Find speakers first."),
    ("speakers", {"pipeline_jobs": [{"type": "audiobook.analyze", "status": "running"}]}, "Wait for Find speakers"),
    ("cast", {}, None),
    ("cast", {"speakers": []}, "no speakers"),
    ("cast", {"speakers": [{"id": "a", "casting": None}, {"id": "b", "casting": None}]}, "2 more speakers"),
    ("audio", {}, None),
    ("audio", {"render_jobs": [{"id": "r", "status": "running"}]}, "1 more chapter"),
    ("audio", {"render_jobs": []}, "Render the book first."),
    ("audio", {"current_source_revision_id": None}, "Add a book first."),
])
def test_a_step_is_approvable_only_once_its_work_is_done(step, overrides, blocker):
    result = approval_blocker(step, _project(**overrides))
    if blocker is None:
        assert result is None
    else:
        assert result is not None and blocker in result


def test_an_approval_holds_until_what_it_covered_changes():
    project = _project()
    settings = {"step_approvals": {
        step: approval_basis(step, project, **INPUTS) for step in ("speakers", "cast", "audio")
    }}
    assert approval_status(settings, project, **INPUTS) == {"speakers": True, "cast": True, "audio": True}

    # Find speakers ran again, a voice changed, a chapter rendered again: each lapses on its own.
    assert approval_status(settings, project, analysis_job_id="analyze-two", render_run_id="run-one")["speakers"] is False
    recast = _project(speakers=[{"id": "narrator", "casting": {"id": "casting-two", "revision": 2}}])
    assert approval_status(settings, recast, **INPUTS) == {"speakers": True, "cast": False, "audio": True}
    rerendered = _project(render_jobs=[{"id": "render-two", "status": "completed"}])
    assert approval_status(settings, rerendered, **INPUTS)["audio"] is False
    # A new open issue withdraws the speaker approval even though the run is the same.
    assert approval_status(settings, _project(review_issues=[{"id": "i"}]), **INPUTS)["speakers"] is False


def test_projects_from_before_approvals_count_as_approved_once_past_the_step():
    assert approval_status({}, _project(), analysis_job_id="a", render_run_id=None) == {
        "speakers": False, "cast": False, "audio": False}
    assert approval_status({}, _project(), analysis_job_id="a", render_run_id="run-one") == {
        "speakers": True, "cast": True, "audio": False}
    assert approval_status({}, _project(state="exported"), analysis_job_id="a", render_run_id="run-one") == {
        "speakers": True, "cast": True, "audio": True}
    # Once one step is approved, a stored approval decides that step only.
    assert approval_status(_approved("cast", _project(), **INPUTS), _project(), **INPUTS)["speakers"] is True
    # Finding speakers again, or new lines to confirm, withdraws an implied approval too.
    running = _project(pipeline_jobs=[{"type": "audiobook.analyze", "status": "running"}])
    assert approval_status({}, running, analysis_job_id="a", render_run_id="run-one")["speakers"] is False
    assert approval_status({}, _project(review_issues=[{"id": "i"}]), analysis_job_id="a",
                           render_run_id="run-one")["speakers"] is False


def test_approving_checks_and_fingerprints_one_read_of_the_project(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from app.apps.audiobook.service import AudiobookService, _latest_analysis_job_id

    saved, views = [], []
    project = _project()

    def view(_self, _work, _context, _project_id, *, include_text):
        views.append(include_text)
        return project, [], "run-one", "analyze-one"

    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=None, commit=lambda: saved.append("commit"))

    monkeypatch.setattr(AudiobookService, "_project_view", view)
    monkeypatch.setattr(AudiobookService, "get_project", lambda *_a, **_k: {"step_approvals": {"speakers": True}})
    monkeypatch.setattr("app.apps.audiobook.service.unit_of_work", work)
    monkeypatch.setattr("app.apps.audiobook.service.PostgresAudiobookProjectRepository.save_step_approval",
                        lambda _self, _context, _project_id, step, basis: saved.append((step, basis)) or True)
    service = AudiobookService(None, None)
    assert service.approve_step(SimpleNamespace(workspace_id="w"), project_id="book", step="speakers") == {"speakers": True}
    assert views == [False]
    assert saved == [("speakers", approval_basis("speakers", project, **INPUTS)), "commit"]

    project = _project(review_issues=[{"id": "i"}])
    saved.clear()
    with pytest.raises(ValueError, match="Confirm the speaker"):
        service.approve_step(SimpleNamespace(workspace_id="w"), project_id="book", step="speakers")
    assert saved == []

    # The latest Find speakers run of any status: a new run, even a failed one, withdraws the approval.
    queries = []
    jobs = SimpleNamespace(query_jobs=lambda *_a, **kwargs: queries.append(kwargs) or [{"id": "analyze-two"}])
    assert _latest_analysis_job_id(SimpleNamespace(jobs=jobs), None, "book", "source") == "analyze-two"
    assert "statuses" not in queries[0] and queries[0]["order_by"] == "created_desc"
