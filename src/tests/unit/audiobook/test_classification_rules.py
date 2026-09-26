from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.audiobook.service import AudiobookService
from app.persistence.blob_store import LocalBlobStore


def test_saved_rules_are_snapshotted_for_initial_import_and_can_be_cleared(tmp_path, monkeypatch):
    settings = {}
    queued = []

    class Connection:
        def execute(self, sql, params):
            if "'{current_ingest_job_id}'" in sql:
                settings["current_ingest_job_id"] = params[0]
                return None
            if "UPDATE omnix_audiobook_projects" in sql:
                assert "classification_rules" in sql
                assert params[1:] == ("workspace", "book")
                settings["classification_rules"] = params[0]
                return SimpleNamespace(fetchone=lambda: ("book",))
            assert "SELECT settings->>'classification_rules'" in sql
            assert "FOR UPDATE" in sql
            return SimpleNamespace(fetchone=lambda: (settings.get("classification_rules"),))

    work = SimpleNamespace(
        connection=Connection(), commit=lambda: None,
        assets=SimpleNamespace(create=lambda *_args: None),
        jobs=SimpleNamespace(create_job=lambda _context, job: queued.append(job)),
    )

    @contextmanager
    def unit_of_work(_database):
        yield work

    monkeypatch.setattr("app.audiobook.service.unit_of_work", unit_of_work)
    monkeypatch.setattr("app.audiobook.service.PostgresAudiobookRepository.get_project", lambda *_args: {"id": "book"})
    service = AudiobookService(None, LocalBlobStore(tmp_path))
    context = SimpleNamespace(workspace_id="workspace")
    rules = "Character quotes can also be in speaker:quote format."
    assert service.save_classification_rules(context, project_id="book", custom_rules=f"  {rules}  ") == {
        "classification_rules": rules,
    }
    service.submit_source(context, project_id="book", source_format="txt", content=b"Ehsan: Hello.", filename="book.txt")
    assert queued[0]["input_payload"]["custom_rules"] == rules
    service.save_classification_rules(context, project_id="book", custom_rules="")
    # Editing book settings must not alter an already queued job's instructions.
    assert queued[0]["input_payload"]["custom_rules"] == rules
    service.submit_source(context, project_id="book", source_format="txt", content=b"Ehsan: Hello.", filename="book.txt")
    assert queued[1]["input_payload"]["custom_rules"] == ""
    assert settings["current_ingest_job_id"] == queued[1]["id"]


@pytest.mark.parametrize("rules", [None, 1, "x" * 4001])
def test_invalid_rules_are_rejected_before_persistence(rules):
    service = AudiobookService(None, None)
    with pytest.raises(ValueError, match="4000 characters"):
        service.save_classification_rules(None, project_id="book", custom_rules=rules)
