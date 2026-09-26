from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.audiobook.extraction import EXTRACTOR_VERSION
from app.audiobook.service import AudiobookService
from app.audiobook.worker import run_ingest_once


@pytest.mark.parametrize("force", [False, True])
def test_quote_extraction_publishes_spans_without_queuing_classification(monkeypatch, force):
    job = {"id": "ingest", "lease_token": "token", "status": "running", "input_payload": {
        "project_id": "book", "source_asset_id": "asset", "source_format": "txt", "custom_rules": "", "force_reclassify": force,
    }}
    completed = []
    published = []
    class Jobs:
        def claim_next(self, *_args, **_kwargs): return job
        def mark_running(self, *_args, **_kwargs): return job
        def get_job(self, *_args): return job
        def update_progress(self, *_args, **_kwargs): pass
        def renew_lease(self, *_args, **_kwargs): pass
        def complete(self, *_args, **kwargs): completed.append(kwargs)
        def fail(self, *_args, **kwargs): raise AssertionError(kwargs)
        def create_job(self, *_args, **_kwargs): raise AssertionError("classification must be requested separately")
        def create_job_once(self, *_args, **_kwargs): raise AssertionError("classification must be requested separately")
    class Connection:
        def execute(self, sql, params):
            if "FROM omnix_assets" in sql:
                return SimpleNamespace(fetchone=lambda: ("key", "checksum"))
            assert "quote_extraction_rules" in sql
            return None
    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=Connection(), jobs=Jobs(), commit=lambda: None, rollback=lambda: None)
    monkeypatch.setattr("app.audiobook.worker.unit_of_work", work)
    monkeypatch.setattr("app.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr("app.audiobook.worker.local_structure_classifier", lambda: None)
    monkeypatch.setattr("app.audiobook.worker._reuse_existing_dialogue_segmentation", lambda *_args: None)
    monkeypatch.setattr("app.audiobook.worker.PostgresAudiobookRepository.append_source_revision", lambda _self, _context, revision, **_kwargs: published.append(revision))
    monkeypatch.setattr("app.audiobook.worker.PostgresAudiobookDocumentStructureRepository.append_analysis", lambda *_args, **_kwargs: "structure")
    assert run_ingest_once(None, SimpleNamespace(read_bytes=lambda *_args, **_kwargs: b'"Hello."'), SimpleNamespace(workspace_id="workspace"), worker_id="worker")
    assert len(published) == 1 and published[0].chapters[0].spans[0].structural_kind == "dialogue"
    assert len(completed) == 1
    assert "Review quote spans" in completed[0]["progress"]["message"]


@pytest.mark.parametrize("extraction_only,rules", [(False, "reviewed rules"), (True, "changed rules"), (False, "changed rules")])
def test_classification_uses_reviewed_spans_and_changed_rules_require_extraction(monkeypatch, extraction_only, rules):
    queued = []
    class Connection:
        def execute(self, sql, _params):
            if "SELECT p.current_source_revision_id" in sql:
                return SimpleNamespace(fetchone=lambda: ("source", None, "asset", "txt", EXTRACTOR_VERSION, {}, "reviewed rules", "reviewed rules"))
            if "SELECT EXISTS" in sql: return SimpleNamespace(fetchone=lambda: (False,))
            if "SELECT id" in sql: return SimpleNamespace(fetchone=lambda: None)
            return SimpleNamespace(fetchone=lambda: ("book",))
    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=Connection(), commit=lambda: None,
                              jobs=SimpleNamespace(create_job=lambda _context, payload: queued.append(payload)))
    monkeypatch.setattr("app.audiobook.service.unit_of_work", work)
    service = AudiobookService(None, None)
    context = SimpleNamespace(workspace_id="workspace")
    if not extraction_only and rules == "changed rules":
        with pytest.raises(ValueError, match="review the quote spans"):
            service.reclassify_source(context, project_id="book", custom_rules=rules)
        assert not queued
    else:
        service.reclassify_source(context, project_id="book", custom_rules=rules, extraction_only=extraction_only)
        assert queued[0]["job_type"] == ("audiobook.ingest" if extraction_only else "audiobook.analyze")
        assert queued[0]["input_payload"]["custom_rules"] == rules
        if not extraction_only:
            assert queued[0]["input_payload"]["source_revision_id"] == "source"
