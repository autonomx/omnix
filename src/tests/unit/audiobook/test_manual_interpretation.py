import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.audiobook.review_repository import PostgresAudiobookReviewRepository
from app.persistence.tenant import local_tenant_context


@pytest.mark.parametrize("previous_revision", [None, 2])
def test_manual_assignment_appends_first_or_next_annotation(previous_revision):
    speaker_id = str(uuid4())
    inserts = []

    class Connection:
        def execute(self, sql, params):
            row = None
            if "SELECT settings->>" in sql:
                row = (None,)
            elif "SELECT s.structural_kind" in sql:
                row = ("dialogue", previous_revision, "dialogue", None, "")
            elif "SELECT id, status" in sql:
                row = (speaker_id, "active")
            elif "INSERT INTO omnix_audiobook_annotations" in sql:
                inserts.append(params)
            return SimpleNamespace(fetchone=lambda: row)

    result = PostgresAudiobookReviewRepository(Connection()).revise_span(
        local_tenant_context(), project_id="book", span_id="span",
        speaker_id=speaker_id, role="dialogue",
    )
    assert result["changed"] is True
    assert result["revision"] == (previous_revision or 0) + 1
    assert inserts[0][5] == speaker_id
    assert json.loads(inserts[0][7])["previous_revision"] == (previous_revision or 0)
